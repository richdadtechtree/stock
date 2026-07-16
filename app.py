import os
import threading
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from market_data import get_snapshot, load_ath_from_history
from trigger_engine import TriggerEngine

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
