# 📈 한국투자증권 API 연동 텔레그램 주가 브리핑 봇 & 대시보드 웹앱

이 프로젝트는 한국투자증권(KIS) API와 Yahoo Finance를 통해 국내외 주요 시장 지수(KOSPI, KOSDAQ, S&P 500)의 실시간 가격과 최고점 대비 등락률(ATH Drawdown)을 수집하여 아름다운 **글래스모피즘 웹 대시보드**에 렌더링하고, 매일 오후 3시 30분에 이 대시보드를 **자동으로 캡처하여 텔레그램 채널로 전송**하는 스케줄러 시스템입니다.

---

## 🛠️ 프로젝트 구조

```text
stock/
├── app.py              # FastAPI 서버 (데이터 API 및 대시보드 웹페이지 서비스)
├── kis_client.py       # 한국투자증권 API OAuth2 및 데이터 요청 클라이언트
├── capture.py          # Playwright 헤드리스 브라우저 자동 캡처 및 텔레그램 전송
├── scheduler.py        # 백그라운드 웹 서버 실행 및 평일 15:30 정기 스케줄러 실행
├── templates/
│   └── index.html      # 실시간 대시보드 HTML (JS로 데이터 수동 렌더링 & SVG 스파크라인 차트)
├── static/
│   └── style.css       # 커스텀 다크 모드 글래스모피즘 테마 CSS
├── .env                # API Key 및 토큰 설정 파일
└── requirements.txt    # 파이썬 라이브러리 의존성
```

---

## 🚀 시작하기

### 1. 환경 설정 파일 작성
프로젝트 폴더 내에 생성된 `.env` 파일을 열어 다음 값을 실제 값으로 수정합니다.

```env
# 1. 텔레그램 봇 토큰 및 수신할 채팅방 ID
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# 2. 한국투자증권 API 키 설정
KIS_CANV_MODE=VIRTUAL      # 실전투자의 경우 REAL, 모의투자의 경우 VIRTUAL
KIS_APP_KEY=your_kis_app_key_here
KIS_APP_SECRET=your_kis_app_secret_here
KIS_ACCOUNT_NO=your_account_no_here  # 계좌번호 (예: 12345678-01)
```

### 2. 브라우저 설치 (Playwright)
화면을 자동으로 캡처하려면 Playwright 브라우저 바이너리 설치가 필요합니다. 터미널에서 다음 명령어를 입력하여 크롬 브라우저를 설치해 주세요.

```bash
playwright install chromium
```

### 3. 테스트 실행 (즉시 캡처 및 텔레그램 전송)
설정이 올바른지 확인하기 위해 아래 명령어를 실행하면, **웹 서버를 켠 뒤 즉시 화면을 캡처하여 텔레그램으로 이미지와 메시지를 발송**하고 종료됩니다.

```bash
python scheduler.py --test
```
*성공적으로 전송되었다면 텔레그램 채널에 고해상도 글래스모피즘 대시보드 이미지가 업로드됩니다.*

### 4. 상시 서비스 실행 (스케줄러)
서버에서 상시 대기하며 매일 월~금요일 15:30에 자동으로 브리핑을 보내려면 다음 명령어를 실행합니다.

```bash
python scheduler.py
```
*백그라운드로 동작시키고 싶다면 `nohup python scheduler.py &` 또는 `pm2 start scheduler.py --name stock-bot` 등으로 실행해 주십시오.*

---

## 🎨 주요 구현 세부사항

* **글래스모피즘 (Glassmorphism) UI**: CSS의 `backdrop-filter`와 반투명 경계선, 네온 그라디언트를 사용하여 고급스러운 금융 대시보드 테마를 구현했습니다.
* **경량 SVG 스파크라인 차트**: 외부 라이브러리(Chart.js 등) 없이 바닐라 자바스크립트로 30일간의 가격 흐름을 부드러운 SVG 곡선 차트로 즉석에서 그려 캡처 해상도에 영향 없이 선명한 차트를 보여줍니다.
* **인증 토큰 캐싱**: KIS API는 24시간 동안 유효하므로 불필요한 토큰 재요청 방지를 위해 `.token_cache.json` 파일에 토큰을 저장하고 자동 갱신합니다.
