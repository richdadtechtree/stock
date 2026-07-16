"""
투자 타이밍 트리거 엔진 (계획서 '계획 2' 구현)

규칙 요약
- 코스피/코스닥 (각각 독립 추적): 역대 최고가 대비 -30/-40/-50/-60/-70% 도달 시
  단계별 알람 (단계당 시드 20%). S&P500이 ATH 대비 -10% 이상 동반 하락 중이면
  해당 회차는 미국 시장에 배분 권고.
- TQQQ 1차 구간: 고점대비 -10%부터 1%p 추가 하락마다 1회, 총 40회 (-10% ~ -49%),
  회차당 시드/40 균등 매수.
- TQQQ 2차 구간: -50% 도달 시점의 현재가 P를 기준으로 0~P를 10등분한 가격을
  하회할 때마다 1회 매수, 회차당 잔여 시드/10. -50%선을 재차 하회하면 P 재설정.
- 신고점(역대 최고가) 갱신 시 해당 종목의 모든 트리거 플래그 리셋.

상태 저장: SQLite (기본 alert_state.db) — 중복 알람 방지.
"""
import os
import sqlite3
from datetime import datetime

DB_PATH = os.getenv("ALERT_DB_PATH", "alert_state.db")

# 코스피/코스닥 분할 매수 단계 (역대 최고가 대비 %)
KR_STAGES = [-30.0, -40.0, -50.0, -60.0, -70.0]
KR_STAGE_RATIO = 20  # 단계당 시드 투자 비중 (%)

# 미국 동반 하락 판정: S&P500 ATH 대비 -10% 이상 하락
US_CRASH_THRESHOLD = -10.0

# TQQQ 1차 구간: -10%부터 1%p 간격 40회 (-10% ~ -49%)
TQQQ_P1_START = 10
TQQQ_P1_COUNT = 40
# TQQQ 2차 구간: -50% 도달 시점 가격 P를 10등분
TQQQ_P2_TRIGGER_DD = -50.0
TQQQ_P2_COUNT = 10

TRACKED = ("KOSPI", "KOSDAQ", "S&P 500", "TQQQ")


class TriggerEngine:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    # ------------------------------------------------------------------ DB
    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS ath_state (
                symbol TEXT PRIMARY KEY,
                ath REAL NOT NULL,
                updated_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS trigger_state (
                symbol TEXT NOT NULL,
                stage TEXT NOT NULL,
                triggered_at TEXT,
                PRIMARY KEY (symbol, stage))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT)""")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _get_ath(conn, symbol):
        row = conn.execute("SELECT ath FROM ath_state WHERE symbol=?", (symbol,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _set_ath(conn, symbol, ath, now_str):
        conn.execute(
            "INSERT INTO ath_state(symbol, ath, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET ath=excluded.ath, updated_at=excluded.updated_at",
            (symbol, ath, now_str))

    @staticmethod
    def _is_triggered(conn, symbol, stage):
        row = conn.execute(
            "SELECT 1 FROM trigger_state WHERE symbol=? AND stage=?", (symbol, stage)).fetchone()
        return row is not None

    @staticmethod
    def _mark(conn, symbol, stage, now_str):
        conn.execute(
            "INSERT OR IGNORE INTO trigger_state(symbol, stage, triggered_at) VALUES(?,?,?)",
            (symbol, stage, now_str))

    @staticmethod
    def _reset_symbol(conn, symbol, prefix=None):
        """트리거 플래그 리셋. prefix 지정 시 해당 접두사 단계만."""
        if prefix:
            conn.execute("DELETE FROM trigger_state WHERE symbol=? AND stage LIKE ?",
                         (symbol, prefix + "%"))
        else:
            conn.execute("DELETE FROM trigger_state WHERE symbol=?", (symbol,))
            if symbol == "TQQQ":
                conn.execute("DELETE FROM meta WHERE key IN ('tqqq_below_50', 'tqqq_p2_base')")

    @staticmethod
    def _get_meta(conn, key):
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _set_meta(conn, key, value):
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))

    # ---------------------------------------------------------- drawdowns
    def _compute_drawdowns(self, conn, snapshot, now_str, readonly=False):
        """
        스냅샷 기준 각 종목의 (drawdown %, current, ath) 계산.
        readonly=False이면 신고점 갱신 시 ATH 저장 + 트리거 리셋 수행.
        """
        dd, cur_px, ath_px = {}, {}, {}
        for sym in TRACKED:
            quote = snapshot.get(sym)
            if not quote:
                continue
            cur = float(quote["current"])
            candidate = max(cur, float(quote.get("ath") or 0))
            stored = self._get_ath(conn, sym)
            if stored is None:
                ath = candidate
                if not readonly:
                    self._set_ath(conn, sym, ath, now_str)
            elif candidate > stored:
                ath = candidate
                if not readonly:
                    # 신고점 갱신 → 이후 하락은 새 고점 기준으로 모든 단계 리셋
                    self._set_ath(conn, sym, ath, now_str)
                    self._reset_symbol(conn, sym)
            else:
                ath = stored
            dd[sym] = (cur - ath) / ath * 100 if ath > 0 else 0.0
            cur_px[sym] = cur
            ath_px[sym] = ath
        return dd, cur_px, ath_px

    # --------------------------------------------------------------- check
    def check(self, snapshot, now=None):
        """
        스냅샷을 평가해 '이번에 새로 도달한' 트리거 이벤트 목록을 반환.
        snapshot: {name: {"current": float[, "ath": float]}}
        반환: [{"symbol", "stage", "message"}]
        """
        now_str = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        events = []
        conn = self._connect()
        try:
            dd, cur_px, ath_px = self._compute_drawdowns(conn, snapshot, now_str)

            us_dd = dd.get("S&P 500")
            us_crash = us_dd is not None and us_dd <= US_CRASH_THRESHOLD

            # ---- 코스피 / 코스닥 (각각 독립 추적)
            for sym in ("KOSPI", "KOSDAQ"):
                if sym not in dd:
                    continue
                for stage in KR_STAGES:
                    key = f"KR{int(stage)}"
                    if dd[sym] <= stage and not self._is_triggered(conn, sym, key):
                        self._mark(conn, sym, key, now_str)
                        if us_crash:
                            allocation = (f"S&P500 동반 하락 중 ({us_dd:.1f}%) "
                                          f"→ 이번 회차는 미국 시장에 배분")
                        else:
                            allocation = f"{sym}에 배분"
                        events.append({
                            "symbol": sym,
                            "stage": key,
                            "message": (
                                f"🚨 *{sym}* 역대 최고가 대비 *{dd[sym]:.1f}%* 도달 "
                                f"(기준선 {int(stage)}%)\n"
                                f"→ 시드 {KR_STAGE_RATIO}% 투자 시점\n"
                                f"→ {allocation}"),
                        })

            # ---- TQQQ
            if "TQQQ" in dd:
                d = dd["TQQQ"]
                cur = cur_px["TQQQ"]

                # 1차 구간: -10% ~ -49%, 1%p 간격 40회
                for n in range(1, TQQQ_P1_COUNT + 1):
                    threshold = -(TQQQ_P1_START + n - 1)
                    key = f"P1-{n:02d}"
                    if d <= threshold and not self._is_triggered(conn, "TQQQ", key):
                        self._mark(conn, "TQQQ", key, now_str)
                        events.append({
                            "symbol": "TQQQ",
                            "stage": key,
                            "message": (
                                f"🚨 *TQQQ* 1차 {n}/{TQQQ_P1_COUNT}회차 매수 시점 "
                                f"(고점대비 {threshold}% 도달, 현재 ${cur:.2f})\n"
                                f"→ 시드의 1/{TQQQ_P1_COUNT} 매수"),
                        })

                # 2차 구간: -50% 이하 → 기준가 P 설정 후 0~P 10등분 매수
                if d <= TQQQ_P2_TRIGGER_DD:
                    if self._get_meta(conn, "tqqq_below_50") != "1":
                        # -50% (재)진입: 기준가 P 재설정 + 2차 트리거 리셋
                        self._set_meta(conn, "tqqq_below_50", "1")
                        self._set_meta(conn, "tqqq_p2_base", str(cur))
                        self._reset_symbol(conn, "TQQQ", prefix="P2-")
                        events.append({
                            "symbol": "TQQQ",
                            "stage": "P2-BASE",
                            "message": (
                                f"⚠️ *TQQQ* 고점대비 -50% 구간 진입 — "
                                f"2차 분할 기준가 P=${cur:.2f} 설정 "
                                f"(0~P 10등분 순차 매수 시작)"),
                        })
                    base = float(self._get_meta(conn, "tqqq_p2_base") or cur)
                    step = base / TQQQ_P2_COUNT
                    for m in range(1, TQQQ_P2_COUNT + 1):
                        trig_price = base - step * m
                        key = f"P2-{m:02d}"
                        if cur <= trig_price and not self._is_triggered(conn, "TQQQ", key):
                            self._mark(conn, "TQQQ", key, now_str)
                            events.append({
                                "symbol": "TQQQ",
                                "stage": key,
                                "message": (
                                    f"🚨 *TQQQ* 2차 {m}/{TQQQ_P2_COUNT}회차 매수 "
                                    f"(트리거가 ${trig_price:.2f} 하회, 현재 ${cur:.2f})\n"
                                    f"→ 잔여 시드의 1/{TQQQ_P2_COUNT} 매수"),
                            })
                else:
                    # -50% 위로 복귀 → 다음 재진입 시 P를 다시 설정하도록 플래그 해제
                    if self._get_meta(conn, "tqqq_below_50") == "1":
                        self._set_meta(conn, "tqqq_below_50", "0")

            conn.commit()
        finally:
            conn.close()
        return events

    # -------------------------------------------------------------- status
    def status(self, snapshot):
        """
        웹앱 '투자 타이밍 현황' 섹션용 상태 조회 (읽기 전용, 트리거 상태 변경 없음).
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        try:
            dd, cur_px, ath_px = self._compute_drawdowns(conn, snapshot, now_str, readonly=True)
            out = {}

            us_dd = dd.get("S&P 500")
            if us_dd is not None:
                out["S&P 500"] = {
                    "current": round(cur_px["S&P 500"], 2),
                    "ath": round(ath_px["S&P 500"], 2),
                    "drawdown": round(us_dd, 2),
                    "us_crash": us_dd <= US_CRASH_THRESHOLD,
                }

            for sym in ("KOSPI", "KOSDAQ"):
                if sym not in dd:
                    continue
                stages = []
                next_stage = None
                for stage in KR_STAGES:
                    key = f"KR{int(stage)}"
                    row = conn.execute(
                        "SELECT triggered_at FROM trigger_state WHERE symbol=? AND stage=?",
                        (sym, key)).fetchone()
                    triggered = row is not None
                    stages.append({
                        "stage": int(stage),
                        "triggered": triggered,
                        "triggered_at": row[0] if row else None,
                    })
                    if not triggered and next_stage is None:
                        next_stage = int(stage)
                done = sum(1 for s in stages if s["triggered"])
                out[sym] = {
                    "current": round(cur_px[sym], 2),
                    "ath": round(ath_px[sym], 2),
                    "drawdown": round(dd[sym], 2),
                    "stages": stages,
                    "done": done,
                    "total": len(KR_STAGES),
                    "next_stage": next_stage,
                    "gap_pp": round(dd[sym] - next_stage, 1) if next_stage is not None else None,
                }

            if "TQQQ" in dd:
                p1_done = conn.execute(
                    "SELECT COUNT(*) FROM trigger_state WHERE symbol='TQQQ' AND stage LIKE 'P1-%'"
                ).fetchone()[0]
                p2_done = conn.execute(
                    "SELECT COUNT(*) FROM trigger_state WHERE symbol='TQQQ' AND stage LIKE 'P2-__'"
                ).fetchone()[0]
                below_50 = self._get_meta(conn, "tqqq_below_50") == "1"
                p2_base = self._get_meta(conn, "tqqq_p2_base")
                p2_base = float(p2_base) if p2_base else None

                next_threshold = None
                if p1_done < TQQQ_P1_COUNT:
                    next_threshold = -(TQQQ_P1_START + p1_done)

                next_price = None
                if below_50 and p2_base and p2_done < TQQQ_P2_COUNT:
                    next_price = round(p2_base - (p2_base / TQQQ_P2_COUNT) * (p2_done + 1), 2)

                out["TQQQ"] = {
                    "current": round(cur_px["TQQQ"], 2),
                    "ath": round(ath_px["TQQQ"], 2),
                    "drawdown": round(dd["TQQQ"], 2),
                    "phase1": {
                        "done": p1_done,
                        "total": TQQQ_P1_COUNT,
                        "next_threshold": next_threshold,
                    },
                    "phase2": {
                        "active": below_50,
                        "base": p2_base,
                        "done": p2_done,
                        "total": TQQQ_P2_COUNT,
                        "next_price": next_price,
                    },
                }
            return out
        finally:
            conn.close()


def format_events(events, now=None):
    """트리거 이벤트 목록을 하나의 텔레그램 메시지로 포맷."""
    if not events:
        return None
    now_str = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"🔔 *투자 타이밍 알림* ({now_str})"
    return header + "\n\n" + "\n\n".join(e["message"] for e in events)


if __name__ == "__main__":
    # 합성 데이터로 동작 확인
    import json
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    engine = TriggerEngine(db_path=tmp.name)

    print("--- 1) 고점 설정 (알람 없음)")
    ev = engine.check({
        "KOSPI": {"current": 3300}, "KOSDAQ": {"current": 1060},
        "S&P 500": {"current": 5600}, "TQQQ": {"current": 90}})
    print(f"events: {len(ev)}")

    print("--- 2) 코스피 -32%, TQQQ -13% (S&P500 -12% 동반 하락)")
    ev = engine.check({
        "KOSPI": {"current": 3300 * 0.68}, "KOSDAQ": {"current": 1060 * 0.75},
        "S&P 500": {"current": 5600 * 0.88}, "TQQQ": {"current": 90 * 0.87}})
    for e in ev:
        print(e["stage"], "|", e["message"].replace("\n", " / "))

    print("--- 3) 동일 스냅샷 재체크 (중복 알람 없음)")
    ev = engine.check({
        "KOSPI": {"current": 3300 * 0.68}, "KOSDAQ": {"current": 1060 * 0.75},
        "S&P 500": {"current": 5600 * 0.88}, "TQQQ": {"current": 90 * 0.87}})
    print(f"events: {len(ev)}")

    print("--- 4) TQQQ -55% (2차 구간 진입)")
    ev = engine.check({"TQQQ": {"current": 90 * 0.45}})
    for e in ev:
        print(e["stage"], "|", e["message"].replace("\n", " / "))

    print("--- 5) 상태 조회")
    st = engine.status({
        "KOSPI": {"current": 3300 * 0.68}, "KOSDAQ": {"current": 1060 * 0.75},
        "S&P 500": {"current": 5600 * 0.88}, "TQQQ": {"current": 90 * 0.45}})
    print(json.dumps(st, indent=2, ensure_ascii=False))
