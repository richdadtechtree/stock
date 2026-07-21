import os
import threading
from datetime import datetime

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from market_data import get_snapshot, load_ath_from_history, get_custom_stocks_snapshot
from trigger_engine import TriggerEngine
from summary import build_summary_text
from capture import capture_dashboard, capture_and_send

load_dotenv()

app = FastAPI(title="Stock Briefing Dashboard API")

# Ensure templates and static directories exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup_event():
    # Load historical ATH values in a background thread
    threading.Thread(target=load_ath_from_history, daemon=True).start()


@app.get("/api/indices")
def get_indices():
    """
    코스피/코스닥/S&P500/TQQQ의 현재가, 등락률, 역대 최고가 대비 하락률 반환.
    국내지수·TQQQ는 한투 API 우선, 실패 시 yfinance 폴백.
    """
    data = get_snapshot(include_sparkline=True)
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
    }


@app.get("/api/alerts")
def get_alerts():
    """
    투자 타이밍 현황 반환 (하락 단계 진행률, 다음 트리거까지 남은 폭 등).
    읽기 전용 — 트리거 발동/알람 전송은 스케줄러(scheduler.py)가 담당.
    """
    snapshot = get_snapshot(include_sparkline=False)
    engine = TriggerEngine()
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": engine.status(snapshot),
    }


@app.get("/api/custom-stocks")
def get_custom_stocks():
    """
    관심 종목 및 ETF의 현재가, 전일대비 등락률, 오늘 알람 여부 반환.
    """
    custom_snapshot = get_custom_stocks_snapshot(use_cache=True)
    engine = TriggerEngine()
    data = engine.get_custom_stocks_status(custom_snapshot)
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
    }


@app.get("/api/summary")
def get_summary():
    """
    현재 시장·투자 타이밍 상황을 사람이 읽기 쉬운 글자로 요약해 반환.
    오픈클로(대화형 봇)가 불러서 그대로 전달하기 좋음.
    """
    text = build_summary_text()
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text": text,
    }


@app.get("/api/screenshot")
def get_screenshot():
    """
    대시보드를 지금 즉시 캡처해 PNG 이미지로 반환 (전송하지 않음).
    오픈클로가 이 이미지를 받아 자기 봇으로 전달할 수 있음.
    """
    path = "static/briefing_screenshot.png"
    if capture_dashboard(path):
        return FileResponse(path, media_type="image/png", filename="market_briefing.png")
    return JSONResponse(status_code=503, content={"status": "error", "message": "capture failed"})


@app.post("/api/briefing/send")
def post_briefing_send(background_tasks: BackgroundTasks):
    """
    지금 즉시 캡처해서 브리핑 봇(봇 1)으로 텔레그램 전송을 예약.
    바로 응답을 돌려주고 전송은 백그라운드에서 진행.
    """
    background_tasks.add_task(capture_and_send)
    return {"status": "accepted", "message": "briefing capture & send started"}


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """
    Serves the main HTML dashboard.
    """
    return FileResponse("templates/index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
