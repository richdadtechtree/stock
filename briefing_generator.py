"""
'월스트리트 나우' 스타일 카드뉴스 브리핑을 자동으로 만드는 모듈.

흐름 (쉽게):
1) 우리 시세를 모아옵니다. (코스피/코스닥/S&P500/TQQQ + 관심 종목)
2) Claude(AI)가 웹 검색으로 그날의 시장 뉴스를 조사해 "해설 글"을 씁니다.
3) AI가 사진(카드뉴스)에 들어갈 내용을 정해진 형식(JSON)으로 만들어 줍니다.
   - 지수 숫자는 우리가 넘겨준 실제 값을 그대로 쓰게 합니다. (지어내지 않게)

이 파일은 "내용"만 만듭니다. 실제 그림(HTML/PNG)은 card_renderer.py 가 그립니다.
"""
import os
import json
from datetime import datetime

from dotenv import load_dotenv

from market_data import get_snapshot, get_custom_stocks_snapshot, load_ath_from_history
from trigger_engine import TriggerEngine

load_dotenv()

# AI 모델 (기본: Claude Opus 5). .env 의 BRIEFING_MODEL 로 바꿀 수 있음.
BRIEFING_MODEL = os.getenv("BRIEFING_MODEL", "claude-opus-5")

# 웹 검색으로 그날 뉴스까지 조사할지 (기본 켬). 끄면 우리 숫자만으로 해설.
BRIEFING_WEB_SEARCH = os.getenv("BRIEFING_WEB_SEARCH", "1") not in ("0", "false", "False", "")


LABELS = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "S&P 500": "S&P 500", "TQQQ": "TQQQ"}


def _fmt_price(name, value):
    if value is None:
        return "-"
    if name == "TQQQ" or (not str(name).isdigit() and name in ("S&P 500",)):
        return f"${value:,.2f}"
    return f"{value:,.2f}"


def gather_market_context():
    """
    AI 에게 넘겨줄 '사실 자료'를 한 덩어리로 모읍니다.
    반환: dict (지수 스냅샷, 관심종목, 투자 타이밍 현황)
    """
    load_ath_from_history()
    snapshot = get_snapshot() or {}
    custom = get_custom_stocks_snapshot() or {}

    engine = TriggerEngine()
    status = engine.status(snapshot) if snapshot else {}

    indices = []
    for key in ("KOSPI", "KOSDAQ", "S&P 500", "TQQQ"):
        d = snapshot.get(key)
        if not d:
            continue
        indices.append({
            "key": key,
            "label": LABELS[key],
            "current": d.get("current"),
            "change_rate": d.get("change_rate"),
            "ath": d.get("ath"),
            "ath_change_rate": d.get("ath_change_rate"),
        })

    custom_list = []
    if custom:
        try:
            cstatus = engine.get_custom_stocks_status(custom)
        except Exception:
            cstatus = {}
        for symbol, s in (cstatus or custom).items():
            is_us = not str(symbol).isdigit()
            cur = s.get("current")
            custom_list.append({
                "symbol": symbol,
                "name": s.get("name", symbol),
                "current": cur,
                "change_rate": s.get("change_rate"),
                "is_us": is_us,
            })

    # 투자 타이밍(우리 알람 규칙) 요약도 함께
    timing = {}
    for key in ("KOSPI", "KOSDAQ", "TQQQ", "S&P 500"):
        if key in status:
            timing[key] = status[key]

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "indices": indices,
        "custom_stocks": custom_list,
        "timing": timing,
    }


# ---- AI 호출 부분 -------------------------------------------------------------

# 카드뉴스 내용의 형식(스키마). AI 가 이 모양 그대로 JSON 을 만들어 줍니다.
CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "kicker": {"type": "string", "description": "상단 소제목 (예: 월스트리트 나우 · WALL STREET NOW)"},
        "headline": {"type": "string", "description": "오늘 브리핑의 큰 제목 (한 줄)"},
        "subheadline": {"type": "string", "description": "부제목. 날짜와 오늘의 핵심을 2~3문장으로 요약"},
        "market_snapshot": {
            "type": "array",
            "description": "상단 지수 카드 4개",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string", "description": "표시용 값 (예: +0.02%). 넘겨준 숫자를 사용"},
                    "direction": {"type": "string", "enum": ["up", "down", "flat"]},
                    "note": {"type": "string", "description": "한 줄 부연 (예: 2거래일 연속 상승)"},
                },
                "required": ["name", "value", "direction", "note"],
                "additionalProperties": False,
            },
        },
        "sections": {
            "type": "array",
            "description": "본문 해설 섹션들 (2~5개)",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "섹션 태그 (예: GEOPOLITICS, MACRO)"},
                    "title": {"type": "string"},
                    "intro": {"type": "string", "description": "섹션 도입 한 줄"},
                    "cards": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "body": {"type": "string", "description": "2~4문장 해설"},
                            },
                            "required": ["title", "body"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["tag", "title", "intro", "cards"],
                "additionalProperties": False,
            },
        },
        "highlight": {
            "type": "object",
            "description": "가운데 강조 콜아웃 (오늘의 핵심 한 방)",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["title", "body"],
            "additionalProperties": False,
        },
        "stocks": {
            "type": "array",
            "description": "개별 종목/ETF 카드 (넘겨준 관심 종목 위주)",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "direction": {"type": "string", "enum": ["up", "down", "flat"]},
                    "note": {"type": "string"},
                },
                "required": ["name", "value", "direction", "note"],
                "additionalProperties": False,
            },
        },
        "timing_note": {
            "type": "string",
            "description": "우리 투자 타이밍(고점 대비 하락 단계) 현황을 한두 문장으로",
        },
        "footer": {"type": "string", "description": "면책/출처 안내 한 줄"},
        "next_checkpoint": {"type": "string", "description": "다음 관전 포인트 (예: 7/30 아마존·애플 실적)"},
    },
    "required": [
        "kicker", "headline", "subheadline", "market_snapshot",
        "sections", "highlight", "stocks", "timing_note", "footer", "next_checkpoint",
    ],
    "additionalProperties": False,
}


def _research_market(client, context):
    """웹 검색으로 그날의 시장 뉴스를 조사해 프로세 노트로 반환. (웹검색 실패 시 빈 문자열)"""
    try:
        prompt = (
            "너는 한국 투자자를 위한 시장 브리핑 애널리스트야. "
            "오늘(" + context["as_of"] + " KST 기준) 미국 증시 마감과 한국 증시, "
            "그리고 반도체(엔비디아·SK하이닉스·삼성전자·필라델피아 반도체지수), "
            "S&P500·나스닥·다우, 금리/FOMC, 주요 지정학 이슈, TQQQ 관련 나스닥100 흐름을 "
            "웹에서 조사해줘. 확인된 사실과 수치 위주로, 한국어로 8~15줄 불릿 메모를 만들어줘. "
            "각 항목은 가능한 한 출처가 있는 사실만. 추측은 '추정'이라고 표시해."
        )
        collected = []
        messages = [{"role": "user", "content": prompt}]
        for _ in range(6):  # pause_turn(서버 도구 반복) 대비 루프
            resp = client.messages.create(
                model=BRIEFING_MODEL,
                max_tokens=8000,
                tools=[{"type": "web_search_20260209", "name": "web_search"}],
                messages=messages,
            )
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    collected.append(block.text)
            if resp.stop_reason == "pause_turn":
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": resp.content},
                ]
                continue
            break
        return "\n".join(t for t in collected if t).strip()
    except Exception as e:
        print(f"[Warn] Web research step failed, continuing without news: {e}")
        return ""


def _compose_content(client, context, research_notes):
    """리서치 노트 + 우리 실제 숫자로 카드뉴스 내용(JSON)을 생성."""
    facts = json.dumps(context, ensure_ascii=False, indent=2)
    system = (
        "너는 '월스트리트 나우' 스타일의 한국어 시장 브리핑 카드뉴스를 만드는 편집자야. "
        "말투는 쉽고 친근하게, 어려운 용어는 풀어서 써. "
        "규칙: (1) market_snapshot 과 stocks 의 지수/종목 숫자는 반드시 아래 '실제 데이터'의 값을 그대로 사용한다(지어내지 말 것). "
        "(2) 해설(sections/highlight)은 리서치 노트의 확인된 사실을 근거로 쓴다. 근거가 약하면 단정하지 말 것. "
        "(3) 특정 종목 매수/매도 추천은 하지 않는다. (4) 전체를 한국어로."
    )
    user = (
        "아래 '실제 데이터'와 '리서치 노트'를 바탕으로 카드뉴스 내용을 JSON 으로 만들어줘.\n\n"
        "market_snapshot 은 지수 4개(코스피/코스닥/S&P 500/TQQQ)를 실제 데이터의 change_rate 로 표시하고, "
        "direction 은 등락 부호에 맞춰줘. value 예시는 '+0.02%' 또는 '-2.23%' 처럼.\n"
        "stocks 는 실제 데이터의 custom_stocks 중 변동이 큰 것 위주로 5~6개 골라. "
        "국내는 '▲+1.2%'처럼, 미국은 부호와 % 로.\n"
        "timing_note 는 실제 데이터의 timing(고점 대비 하락 단계)을 한두 문장으로 풀어줘.\n\n"
        f"=== 실제 데이터 ===\n{facts}\n\n"
        f"=== 리서치 노트 ===\n{research_notes or '(웹 검색 결과 없음 — 실제 데이터와 일반적 시장 맥락으로 작성)'}\n"
    )
    resp = client.messages.create(
        model=BRIEFING_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CONTENT_SCHEMA}},
    )
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise RuntimeError("AI 가 카드 내용을 만들지 못했습니다 (빈 응답).")
    return json.loads(text)


def generate_briefing_content(context=None):
    """
    카드뉴스에 들어갈 내용(dict)을 AI 로 생성해 반환.
    ANTHROPIC_API_KEY (또는 `ant auth login` 프로필) 필요.
    """
    import anthropic

    if context is None:
        context = gather_market_context()

    client = anthropic.Anthropic()
    research_notes = _research_market(client, context) if BRIEFING_WEB_SEARCH else ""
    content = _compose_content(client, context, research_notes)
    content["_as_of"] = context["as_of"]
    return content


def build_card_briefing(send=True):
    """
    카드뉴스 브리핑을 처음부터 끝까지 만듭니다.
    1) 시세 수집 → 2) AI 내용 생성 → 3) HTML 렌더 → 4) PNG 캡처 → (5) 텔레그램 전송)
    반환: PNG 경로(성공) 또는 None(실패)
    """
    from card_renderer import write_html
    from capture import capture_html_file, CARD_HTML_PATH, CARD_SCREENSHOT_PATH

    context = gather_market_context()
    if not context["indices"]:
        print("[Error] 시세를 가져오지 못해 브리핑을 만들 수 없습니다.")
        return None

    print("AI 로 카드뉴스 내용을 생성하는 중...")
    content = generate_briefing_content(context)

    write_html(content, CARD_HTML_PATH)
    if not capture_html_file(CARD_HTML_PATH, CARD_SCREENSHOT_PATH):
        return None

    if send:
        from notifier import send_telegram_photo
        date_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
        caption = (
            f"📰 *월스트리트 나우 스타일 브리핑*\n"
            f"📅 {date_str} 기준\n\n"
            f"{content.get('headline', '')}"
        )
        if send_telegram_photo(CARD_SCREENSHOT_PATH, caption):
            print("카드뉴스 브리핑을 텔레그램으로 전송했습니다!")
        else:
            print("[Warn] 텔레그램 전송 실패 (PNG 는 저장됨).")

    return CARD_SCREENSHOT_PATH


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ctx = gather_market_context()
    print(json.dumps(generate_briefing_content(ctx), ensure_ascii=False, indent=2))
