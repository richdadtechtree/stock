"""
현재 시장·투자 타이밍 상황을 사람이 읽기 쉬운 글자로 요약.
오픈클로(대화형 봇)가 /api/summary 로 불러 텍스트 그대로 전달할 수 있음.
"""
from datetime import datetime

from market_data import get_snapshot
from trigger_engine import TriggerEngine


def build_summary_text():
    """현재 스냅샷 + 트리거 현황을 마크다운 텍스트로 반환."""
    snapshot = get_snapshot()
    if not snapshot:
        return "⚠️ 지금은 시세를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요."

    status = TriggerEngine().status(snapshot)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 *시장 브리핑* ({now})", ""]

    # 지수/종목 현재가 요약
    label = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "S&P 500": "S&P500", "TQQQ": "TQQQ"}
    for key in ("KOSPI", "KOSDAQ", "S&P 500", "TQQQ"):
        d = snapshot.get(key)
        if not d:
            continue
        cur = d["current"]
        chg = d["change_rate"]
        dd = d["ath_change_rate"]
        price = f"${cur:,.2f}" if key == "TQQQ" else f"{cur:,.2f}"
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(f"• {label[key]}: {price}  {arrow}{chg:+.2f}% (고점대비 {dd:.1f}%)")

    # 투자 타이밍 요약
    lines.append("")
    lines.append("🔔 *투자 타이밍*")

    for key in ("KOSPI", "KOSDAQ"):
        s = status.get(key)
        if not s:
            continue
        if s["next_stage"] is not None:
            nxt = f"다음 -{abs(s['next_stage'])}% (앞으로 {abs(s['gap_pp']):.1f}%p)"
        else:
            nxt = "모든 단계 완료"
        lines.append(f"• {label[key]}: {s['done']}/{s['total']}단계 도달 · {nxt}")

    t = status.get("TQQQ")
    if t:
        if t["phase2"]["active"]:
            nxt = (f"다음 매수 ${t['phase2']['next_price']:.2f} 이하"
                   if t["phase2"]["next_price"] is not None else "2차 완료")
            lines.append(f"• TQQQ: 2차 구간 {t['phase2']['done']}/{t['phase2']['total']}회차 · {nxt}")
        else:
            nt = t["phase1"]["next_threshold"]
            nxt = f"다음 매수 {nt}%" if nt is not None else "1차 완료"
            lines.append(f"• TQQQ: 1차 {t['phase1']['done']}/{t['phase1']['total']}회차 · {nxt}")

    sp = status.get("S&P 500")
    if sp:
        crash = "동반 하락 중 (미국 배분 조건 충족)" if sp["us_crash"] else "동반 하락 아님"
        lines.append(f"• S&P500: 고점대비 {sp['drawdown']:.1f}% · {crash}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_summary_text())
