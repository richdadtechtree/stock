# 📈 한국투자증권 API 연동 텔레그램 주가 브리핑 봇 & 대시보드 웹앱

이 프로젝트는 한국투자증권(KIS) API와 Yahoo Finance를 통해 국내외 주요 시장 지수(KOSPI, KOSDAQ, S&P 500)와 **TQQQ**의 실시간 가격과 최고점 대비 등락률(ATH Drawdown)을 수집하여 **글래스모피즘 웹 대시보드**에 렌더링하고,

1. 매일 오후 3시 30분에 대시보드를 **자동 캡처하여 텔레그램으로 전송**하고 (정기 브리핑)
2. 고점 대비 하락률이 분할 매수 기준선에 도달하면 **투자 타이밍 알람을 텔레그램으로 전송**하는 (조건 알람)

스케줄러 시스템입니다.

---

## 🛠️ 프로젝트 구조

```text
stock/
├── app.py              # FastAPI 서버 (시세/알람 API 및 대시보드 웹페이지)
├── kis_client.py       # 한국투자증권 API OAuth2 + 국내지수/해외주식 시세 클라이언트
├── market_data.py      # 공용 시세 수집 모듈 (KIS 우선, yfinance 폴백, ATH 캐시)
├── trigger_engine.py   # 투자 타이밍 트리거 엔진 (SQLite 상태 저장, 중복 알람 방지)
├── notifier.py         # 텔레그램 메시지/사진 전송 모듈
├── capture.py          # Playwright 헤드리스 브라우저 자동 캡처
├── scheduler.py        # 웹서버 + 15:30 브리핑 + 주기적 트리거 체크 스케줄러
├── backtest.py         # 과거 데이터로 트리거 알람 시뮬레이션 (백테스트)
├── templates/
│   └── index.html      # 대시보드 HTML (지수 카드 + 투자 타이밍 현황 섹션)
├── static/
│   └── style.css       # 다크 모드 글래스모피즘 테마 CSS
├── .env                # API Key 및 토큰 설정 파일
└── requirements.txt    # 파이썬 라이브러리 의존성
```

---

## 🔔 투자 타이밍 알람 규칙

모든 하락률은 **역대 최고가(ATH)** 기준이며, 신고점 갱신 시 모든 단계가 새 고점 기준으로 리셋됩니다.
트리거 상태는 `alert_state.db`(SQLite)에 저장되어 **같은 단계에서 중복 알람이 발생하지 않습니다.**

### 코스피 / 코스닥 (각각 독립 추적)

| 하락률 단계 | 회차당 투자 비중 |
|:---:|:---:|
| -30% / -40% / -50% / -60% / -70% | 시드의 20% |

- S&P500이 ATH 대비 **-10% 이상 동반 하락 중**이면 해당 회차는 **미국 시장 배분**을 권고합니다.

### TQQQ

- **1차 구간**: 고점대비 -10%부터 **1%p 하락마다 1회**, 총 40회 (-10% ~ -49%), 회차당 시드/40
- **2차 구간**: -50% 도달 시점의 현재가 **P를 0~P로 10등분**한 가격을 하회할 때마다 1회, 회차당 잔여 시드/10
- -50%선을 재차 하회하면 그 시점의 현재가로 P를 재설정합니다.

---

## 🚀 시작하기

### 1. 환경 설정 파일 작성
프로젝트 폴더 내에 `.env` 파일을 만들고 다음 값을 실제 값으로 수정합니다.

```env
# 1. 텔레그램 봇 토큰 및 수신할 채팅방 ID
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# 2. 한국투자증권 API 키 설정
KIS_CANV_MODE=VIRTUAL      # 실전투자의 경우 REAL, 모의투자의 경우 VIRTUAL
KIS_APP_KEY=your_kis_app_key_here
KIS_APP_SECRET=your_kis_app_secret_here
KIS_ACCOUNT_NO=your_account_no_here  # 계좌번호 (예: 12345678-01)

# 3. (선택) 투자 타이밍 트리거 체크 주기 (분, 기본 10분)
ALERT_CHECK_INTERVAL_MIN=10
```

#### 텔레그램 봇 만들기 (아직 안 했다면)
1. 텔레그램에서 **@BotFather** 검색 → `/newbot` → 봇 이름/아이디 입력 → **BOT_TOKEN** 발급
2. 만든 봇에게 아무 메시지나 1개 전송 (또는 봇을 채널/그룹에 초대)
3. 브라우저에서 `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` 접속 → `"chat":{"id": ...}` 값이 **CHAT_ID**

### 2. 브라우저 설치 (Playwright)
```bash
playwright install chromium
```

### 3. 테스트 실행

```bash
# 캡처 + 텔레그램 전송 즉시 테스트
python scheduler.py --test

# 투자 타이밍 트리거 체크 1회 즉시 실행 (도달한 단계가 있으면 텔레그램 알람)
python scheduler.py --check-alerts
```

### 4. 상시 서비스 실행 (스케줄러)
```bash
python scheduler.py
```
- 평일 15:30 — 마감 브리핑 캡처 → 텔레그램 전송
- 매 10분(설정 가능) — 하락률 트리거 체크 → 새 단계 도달 시 텔레그램 알람

*백그라운드 동작은 `nohup python scheduler.py &` 또는 `pm2 start scheduler.py --name stock-bot` 등으로 실행해 주십시오.*

### 5. 백테스트 (과거 데이터로 알람 시뮬레이션)
실제 하락장이 오기 전에 트리거 로직을 검증할 수 있습니다. 실제 알람 DB에는 영향을 주지 않습니다.

```bash
python backtest.py --start 2021-11-01 --end 2023-01-01   # 2022년 하락장 시뮬레이션
```

---

## 🌐 API 엔드포인트

| 경로 | 설명 |
|------|------|
| `/` | 대시보드 웹페이지 |
| `/api/indices` | 코스피/코스닥/S&P500/TQQQ 현재가, 등락률, ATH 하락률, 스파크라인 |
| `/api/alerts` | 투자 타이밍 현황 (단계 진행률, 다음 트리거까지 남은 폭) |

---

## 🎨 주요 구현 세부사항

* **공용 시세 수집 (`market_data.py`)**: 국내지수·TQQQ는 한투 API 우선, 실패 시 yfinance 폴백. 스냅샷 60초 캐시로 중복 호출 방지.
* **트리거 엔진 (`trigger_engine.py`)**: 종목·단계별 트리거 플래그를 SQLite에 저장해 중복 알람 방지. 신고점 갱신 시 자동 리셋, TQQQ -50% 재진입 시 기준가 P 재설정.
* **글래스모피즘 (Glassmorphism) UI**: CSS `backdrop-filter`와 네온 그라디언트 기반 금융 대시보드 테마.
* **경량 SVG 스파크라인 차트**: 외부 라이브러리 없이 30일 가격 흐름을 SVG로 렌더링.
* **인증 토큰 캐싱**: KIS 토큰을 `.token_cache.json`에 저장하고 자동 갱신.
