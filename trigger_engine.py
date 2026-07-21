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

    def check_sidecars(self, snapshot, now=None):
        """
        코스피 및 코스닥 지수의 당일 등락률을 평가해 사이드카 조건(코스피 ±5%, 코스닥 ±6%)을
        돌파했는지 검사하여 이벤트를 반환합니다. 하루에 한 번씩만 알림이 전송됩니다.
        """
        now_dt = datetime.now()
        date_str = now_dt.strftime("%Y-%m-%d")
        now_str = now or now_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        events = []
        conn = self._connect()
        try:
            # 1. KOSPI 검사 (±5%)
            if "KOSPI" in snapshot:
                chg = snapshot["KOSPI"]["change_rate"]
                current = snapshot["KOSPI"]["current"]
                if chg >= 5.0:
                    stage_key = f"SIDECAR_RISE_{date_str}"
                    if not self._is_triggered(conn, "KOSPI", stage_key):
                        self._mark(conn, "KOSPI", stage_key, now_str)
                        events.append({
                            "symbol": "KOSPI",
                            "stage": stage_key,
                            "message": (
                                f"🚨 *[사이드카 발동 조건 돌파 - 코스피]*\n"
                                f"코스피 선물 시장 변동성으로 인한 사이드카 발동 기준(±5.0%)을 돌파했습니다.\n"
                                f"현재 코스피 등락률: *{chg:+.2f}%* (현재가: {current:,.2f})"
                            )
                        })
                elif chg <= -5.0:
                    stage_key = f"SIDECAR_FALL_{date_str}"
                    if not self._is_triggered(conn, "KOSPI", stage_key):
                        self._mark(conn, "KOSPI", stage_key, now_str)
                        events.append({
                            "symbol": "KOSPI",
                            "stage": stage_key,
                            "message": (
                                f"🚨 *[사이드카 발동 조건 돌파 - 코스피]*\n"
                                f"코스피 선물 시장 변동성으로 인한 사이드카 발동 기준(±5.0%)을 돌파했습니다.\n"
                                f"현재 코스피 등락률: *{chg:+.2f}%* (현재가: {current:,.2f})"
                            )
                        })
            
            # 2. KOSDAQ 검사 (±6%)
            if "KOSDAQ" in snapshot:
                chg = snapshot["KOSDAQ"]["change_rate"]
                current = snapshot["KOSDAQ"]["current"]
                if chg >= 6.0:
                    stage_key = f"SIDECAR_RISE_{date_str}"
                    if not self._is_triggered(conn, "KOSDAQ", stage_key):
                        self._mark(conn, "KOSDAQ", stage_key, now_str)
                        events.append({
                            "symbol": "KOSDAQ",
                            "stage": stage_key,
                            "message": (
                                f"🚨 *[사이드카 발동 조건 돌파 - 코스닥]*\n"
                                f"코스닥 선물 시장 변동성으로 인한 사이드카 발동 기준(±6.0%)을 돌파했습니다.\n"
                                f"현재 코스닥 등락률: *{chg:+.2f}%* (현재가: {current:,.2f})"
                            )
                        })
                elif chg <= -6.0:
                    stage_key = f"SIDECAR_FALL_{date_str}"
                    if not self._is_triggered(conn, "KOSDAQ", stage_key):
                        self._mark(conn, "KOSDAQ", stage_key, now_str)
                        events.append({
                            "symbol": "KOSDAQ",
                            "stage": stage_key,
                            "message": (
                                f"🚨 *[사이드카 발동 조건 돌파 - 코스닥]*\n"
                                f"코스닥 선물 시장 변동성으로 인한 사이드카 발동 기준(±6.0%)을 돌파했습니다.\n"
                                f"현재 코스닥 등락률: *{chg:+.2f}%* (현재가: {current:,.2f})"
                            )
                        })
            conn.commit()
        finally:
            conn.close()
        return events

    def check_custom_stocks(self, custom_snapshot, now=None):
        """
        커스텀 관심 종목들의 당일 등락률을 평가해 알림 조건에 도달한 종목이 있으면 이벤트를 반환합니다.
        모든 관심 종목 및 ETF에 대해 2% 단위(2%, 4%, 6%, 8%, 10%...) 누적 등락 알림을 전송합니다.
        (10% 이상 등락 시 🚨 대폭등/대폭락으로 강조 전송)
        """
        if now:
            try:
                now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
            except Exception:
                now_dt = datetime.now()
        else:
            now_dt = datetime.now()
        date_str = now_dt.strftime("%Y-%m-%d")
        now_str = now or now_dt.strftime("%Y-%m-%d %H:%M:%S")

        try:
            step_unit = float(os.getenv("CUSTOM_ALERT_STEP", os.getenv("CUSTOM_ALERT_THRESHOLD", "2.0")))
        except ValueError:
            step_unit = 2.0

        events = []
        conn = self._connect()
        try:
            for symbol, data in custom_snapshot.items():
                change_rate = data["change_rate"]
                name = data["name"]
                current = data["current"]
                is_etf = data.get("is_etf", False)
                type_str = "ETF" if is_etf else "종목"

                # 1. 달성한 모든 2% 단위 단계 계산 (예: 2%, 4%, 6%, 8%, 10%...)
                steps = []
                if change_rate >= step_unit:
                    curr = step_unit
                    while curr <= change_rate:
                        steps.append((round(curr, 1), "RISE"))
                        curr += step_unit
                elif change_rate <= -step_unit:
                    curr = -step_unit
                    while curr >= change_rate:
                        steps.append((round(abs(curr), 1), "FALL"))
                        curr -= step_unit

                # 2. 각 단계에 대해 아직 트리거되지 않은 알림을 체크
                for val, direction in steps:
                    stage_key = f"{direction}_STEP_{val:.1f}_{date_str}"
                    if not self._is_triggered(conn, symbol, stage_key):
                        self._mark(conn, symbol, stage_key, now_str)

                        is_major = val >= 10.0
                        if direction == "RISE":
                            dir_str = "🚨 대폭등" if is_major else "급등"
                            dir_emoji = "🚀🚨" if is_major else "🚀"
                            sign = "+"
                        else:
                            dir_str = "🚨 대폭락" if is_major else "급락"
                            dir_emoji = "📉🚨" if is_major else "📉"
                            sign = "-"

                        formatted_price = f"${current:,.2f}" if not symbol.isdigit() else f"{current:,.0f}원"

                        events.append({
                            "symbol": symbol,
                            "stage": stage_key,
                            "message": (
                                f"{dir_emoji} *[{name} ({symbol})] {type_str} {dir_str} 알림*\n"
                                f"전일 대비 *{sign}{val:.0f}%* 돌파! (현재 등락률: {change_rate:+.2f}%)\n"
                                f"현재가: {formatted_price}"
                            )
                        })
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

    def get_custom_stocks_status(self, custom_snapshot):
        """
        관심 종목들의 오늘 알람 트리거 상태를 반환합니다.
        """
        now_dt = datetime.now()
        date_str = now_dt.strftime("%Y-%m-%d")
        conn = self._connect()
        out = {}
        try:
            for symbol, data in custom_snapshot.items():
                triggered_steps = []
                rows = conn.execute(
                    "SELECT stage FROM trigger_state WHERE symbol=? AND (stage LIKE 'RISE_STEP_%' OR stage LIKE 'FALL_STEP_%') AND stage LIKE ?",
                    (symbol, f"%_{date_str}")
                ).fetchall()

                for r in rows:
                    stage = r[0]
                    parts = stage.split("_")
                    try:
                        val = float(parts[2])
                        direction = "RISE" if "RISE" in stage else "FALL"
                        triggered_steps.append({"val": val, "direction": direction})
                    except Exception:
                        pass

                triggered_steps.sort(key=lambda x: x["val"])

                out[symbol] = {
                    "name": data["name"],
                    "current": data["current"],
                    "change_rate": data["change_rate"],
                    "is_etf": data["is_etf"],
                    "source": data["source"],
                    "is_step_alert": True,
                    "triggered_steps": triggered_steps,
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


def format_sidecar_events(events, now=None):
    """사이드카 발동 이벤트 목록을 하나의 텔레그램 메시지로 포맷."""
    if not events:
        return None
    now_str = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"🚨 *시장 변동성 경보 (사이드카)* ({now_str})"
    return header + "\n\n" + "\n\n".join(e["message"] for e in events)


def format_custom_events(events, now=None):
    """관심 종목 변동 이벤트 목록을 하나의 텔레그램 메시지로 포맷."""
    if not events:
        return None
    now_str = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"📢 *관심 종목 변동 알림* ({now_str})"
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
