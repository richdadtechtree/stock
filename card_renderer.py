"""
카드뉴스 내용(dict) → '월스트리트 나우' 스타일 HTML 문자열로 그리는 모듈.

briefing_generator.py 가 만든 내용을 받아 사진과 비슷한 레이아웃의 HTML 을 만듭니다.
이 HTML 을 capture.py 가 PNG 로 찍고, notifier.py 가 텔레그램으로 보냅니다.
"""
import html


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _dir_class(direction):
    return {"up": "up", "down": "down", "flat": "flat"}.get(direction, "flat")


def _stat_card(item):
    d = _dir_class(item.get("direction"))
    return f"""
      <div class="stat">
        <div class="stat-name">{_esc(item.get('name'))}</div>
        <div class="stat-value {d}">{_esc(item.get('value'))}</div>
        <div class="stat-note">{_esc(item.get('note'))}</div>
      </div>"""


def _section(sec):
    cards = "".join(
        f"""
        <div class="card">
          <div class="card-title">{_esc(c.get('title'))}</div>
          <div class="card-body">{_esc(c.get('body'))}</div>
        </div>"""
        for c in sec.get("cards", [])
    )
    return f"""
    <section class="block">
      <div class="block-head">
        <span class="tag">{_esc(sec.get('tag'))}</span>
        <h2>{_esc(sec.get('title'))}</h2>
      </div>
      <p class="intro">{_esc(sec.get('intro'))}</p>
      <div class="cards">{cards}</div>
    </section>"""


def render_html(content):
    """내용(dict) → 완성된 HTML 문자열."""
    kicker = _esc(content.get("kicker", "월스트리트 나우 · WALL STREET NOW"))
    headline = _esc(content.get("headline", "오늘의 시장 브리핑"))
    subheadline = _esc(content.get("subheadline", ""))

    snapshot = "".join(_stat_card(s) for s in content.get("market_snapshot", []))
    sections = "".join(_section(s) for s in content.get("sections", []))

    hl = content.get("highlight") or {}
    highlight = ""
    if hl.get("title") or hl.get("body"):
        highlight = f"""
    <section class="highlight">
      <div class="hl-title">{_esc(hl.get('title'))}</div>
      <div class="hl-body">{_esc(hl.get('body'))}</div>
    </section>"""

    stocks = "".join(_stat_card(s) for s in content.get("stocks", []))
    stocks_block = ""
    if stocks:
        stocks_block = f"""
    <section class="block">
      <div class="block-head">
        <span class="tag">STOCKS</span>
        <h2>개별 종목과 관심 자산</h2>
      </div>
      <div class="stats stocks">{stocks}</div>
    </section>"""

    timing_note = content.get("timing_note")
    timing_block = ""
    if timing_note:
        timing_block = f"""
    <section class="timing">
      <span class="tag alt">투자 타이밍</span>
      <p>{_esc(timing_note)}</p>
    </section>"""

    footer = _esc(content.get("footer", "본 자료는 정보 공유 목적이며 투자 권유가 아닙니다. 투자 판단과 책임은 본인에게 있습니다."))
    next_cp = _esc(content.get("next_checkpoint", ""))
    as_of = _esc(content.get("_as_of", ""))

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic",
                 "Noto Sans KR", "Segoe UI", sans-serif;
    background:#eef1f6; color:#1e2430; line-height:1.55;
    -webkit-font-smoothing:antialiased;
  }}
  .page {{ width:1000px; margin:0 auto; background:#f4f6fa; }}

  /* 헤더 (보라 그라데이션) */
  .hero {{
    background:linear-gradient(120deg,#2b2f6b 0%, #4b3fb0 55%, #6d5be0 100%);
    color:#fff; padding:40px 48px 44px;
  }}
  .kicker {{ font-size:13px; letter-spacing:3px; text-transform:uppercase;
            opacity:.85; font-weight:700; margin-bottom:14px; }}
  .hero h1 {{ font-size:38px; line-height:1.2; font-weight:800; margin-bottom:16px; }}
  .hero .sub {{ font-size:16px; opacity:.9; max-width:820px; }}

  .body {{ padding:34px 48px 40px; }}

  /* 지수 스냅샷 카드 */
  .snap-label {{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }}
  .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:34px; }}
  .stats.stocks {{ grid-template-columns:repeat(3,1fr); }}
  .stat {{ background:#fff; border-radius:14px; padding:18px 20px;
           box-shadow:0 2px 10px rgba(30,40,70,.06); border:1px solid #eaedf3; }}
  .stat-name {{ font-size:14px; color:#6b7280; font-weight:600; margin-bottom:8px; }}
  .stat-value {{ font-size:26px; font-weight:800; margin-bottom:6px; }}
  .stat-value.up {{ color:#e0342f; }}      /* 한국식: 상승=빨강 */
  .stat-value.down {{ color:#1466d6; }}     /* 하락=파랑 */
  .stat-value.flat {{ color:#4b5563; }}
  .stat-note {{ font-size:12.5px; color:#9299a5; }}

  /* 본문 섹션 */
  .block {{ margin-bottom:34px; }}
  .block-head {{ display:flex; align-items:center; gap:12px; margin-bottom:8px; }}
  .block-head h2 {{ font-size:23px; font-weight:800; }}
  .tag {{ font-size:11px; font-weight:800; letter-spacing:1.5px; text-transform:uppercase;
          color:#5b4fd1; background:#ece9fb; padding:5px 11px; border-radius:7px; }}
  .tag.alt {{ color:#b06a00; background:#fbf0dd; }}
  .intro {{ font-size:15px; color:#5b6472; margin-bottom:16px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
  .card {{ background:#fff; border-radius:14px; padding:20px 22px;
           border:1px solid #eaedf3; border-left:5px solid #6d5be0;
           box-shadow:0 2px 10px rgba(30,40,70,.05); }}
  .card-title {{ font-size:16px; font-weight:800; margin-bottom:8px; }}
  .card-body {{ font-size:14px; color:#4b5563; }}

  /* 가운데 강조 콜아웃 */
  .highlight {{ background:#fdeff0; border:1px solid #f6d3d5; border-radius:16px;
               padding:26px 30px; text-align:center; margin-bottom:34px; }}
  .hl-title {{ font-size:22px; font-weight:800; color:#c0322e; margin-bottom:10px; }}
  .hl-body {{ font-size:15px; color:#5b3436; max-width:760px; margin:0 auto; }}

  /* 투자 타이밍 */
  .timing {{ background:#f3f6fc; border:1px solid #e2e8f4; border-radius:14px;
            padding:20px 24px; margin-bottom:30px; }}
  .timing p {{ font-size:14.5px; color:#334155; margin-top:10px; }}

  /* 푸터 */
  .foot {{ border-top:1px solid #e3e7ef; padding-top:18px; display:flex;
           justify-content:space-between; align-items:center; gap:16px; }}
  .foot .disc {{ font-size:12px; color:#9299a5; max-width:620px; }}
  .foot .cp {{ font-size:13px; font-weight:700; color:#fff; background:#1f2430;
              padding:10px 16px; border-radius:10px; white-space:nowrap; }}
  .asof {{ font-size:12px; color:#c9cfdb; margin-top:16px; text-align:right; padding:0 48px 24px; }}
</style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <div class="kicker">{kicker}</div>
      <h1>{headline}</h1>
      <div class="sub">{subheadline}</div>
    </div>

    <div class="body">
      <div class="snap-label"><span class="tag">MARKET</span><h2 style="font-size:20px;font-weight:800;">오늘의 시장 스냅샷</h2></div>
      <div class="stats">{snapshot}</div>

      {sections}
      {highlight}
      {stocks_block}
      {timing_block}

      <div class="foot">
        <div class="disc">{footer}</div>
        <div class="cp">다음 관전 포인트 · {next_cp}</div>
      </div>
    </div>
    <div class="asof">기준: {as_of} · 자동 생성 브리핑</div>
  </div>
</body>
</html>"""


def write_html(content, path="static/card_briefing.html"):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    html_str = render_html(content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_str)
    return path
