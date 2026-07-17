import os
import sys
import time
import threading
import argparse
import uvicorn
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler

from capture import capture_and_send
from market_data import get_snapshot, load_ath_from_history
from trigger_engine import TriggerEngine, format_events
from notifier import send_telegram_message

load_dotenv()

# Server config
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "127.0.0.1")

# 투자 타이밍 트리거 체크 주기 (분)
ALERT_CHECK_INTERVAL_MIN = int(os.getenv("ALERT_CHECK_INTERVAL_MIN", "10"))


def run_server():
    """
    Runs the FastAPI Uvicorn server.
    """
    print(f"Starting FastAPI Web Server at http://{HOST}:{PORT}")
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="warning")


def daily_job():
    """
    Triggered daily at 15:30 — 대시보드 캡처 후 텔레그램 전송.
    """
    print(f"[{datetime.now()}] Starting scheduled daily briefing capture...")
    success = capture_and_send()
    print(f"[{datetime.now()}] Scheduled job completed. Status: {'SUCCESS' if success else 'FAILED'}")


def alert_job():
    """
    투자 타이밍 트리거 체크 — 새로 도달한 하락 단계가 있으면 텔레그램 알람 전송.
    """
    print(f"[{datetime.now()}] Checking investment timing triggers...")
    try:
        snapshot = get_snapshot()
        if not snapshot:
            print("[Warn] Empty market snapshot. Skipping trigger check.")
            return
        engine = TriggerEngine()
        events = engine.check(snapshot)
        if events:
            message = format_events(events)
            sent = send_telegram_message(message)
            print(f"[{datetime.now()}] {len(events)} trigger(s) fired. "
                  f"Telegram: {'SENT' if sent else 'FAILED'}")
        else:
            print(f"[{datetime.now()}] No new triggers.")
    except Exception as e:
        print(f"[Error] alert_job failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Stock Briefing Bot Scheduler & Server")
    parser.add_argument("--test", action="store_true",
                        help="Run the capture and send function immediately and exit")
    parser.add_argument("--check-alerts", action="store_true",
                        help="Run the investment timing trigger check immediately and exit")
    parser.add_argument("--summary", action="store_true",
                        help="Print the current market & timing summary text and exit")
    args = parser.parse_args()

    if args.summary:
        from summary import build_summary_text
        load_ath_from_history()
        print(build_summary_text())
        sys.exit(0)

    if args.check_alerts:
        print("--- Running Alert Check Mode ---")
        load_ath_from_history()
        alert_job()
        print("Exiting alert check mode.")
        sys.exit(0)

    # Start FastAPI server in a background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to boot up
    time.sleep(3)

    if args.test:
        print("--- Running Test Mode ---")
        print("Triggering capture and send immediately...")
        success = capture_and_send()
        print(f"Test Run Completed. Status: {'SUCCESS' if success else 'FAILED'}")
        print("Exiting test mode.")
        sys.exit(0)

    # ATH 초기 로딩 (트리거 판정 정확도를 위해 시작 시 1회)
    load_ath_from_history()

    # Initialize APScheduler
    # 서버 시간이 UTC여도 항상 '한국시간(KST)' 기준으로 돌도록 타임존을 고정.
    # (이걸 안 하면 15:30이 서버 UTC 15:30 = 한국 00:30에 실행되는 문제 발생)
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # Schedule job: Monday to Friday at 15:30 — 마감 브리핑 캡처 전송
    scheduler.add_job(
        daily_job,
        'cron',
        day_of_week='mon-fri',
        hour=15,
        minute=30,
        id='daily_briefing',
        name='Daily Stock Market Briefing at 15:30'
    )

    # Schedule job: 투자 타이밍 트리거 체크 (미장 시간대 포함 24시간 주기 체크)
    scheduler.add_job(
        alert_job,
        'interval',
        minutes=ALERT_CHECK_INTERVAL_MIN,
        id='alert_check',
        name=f'Investment Timing Trigger Check (every {ALERT_CHECK_INTERVAL_MIN} min)'
    )

    print("--------------------------------------------------")
    print("Stock Briefing Scheduler is now running.")
    print("Schedule: Mon-Fri at 15:30 KST (briefing capture)")
    print(f"Schedule: every {ALERT_CHECK_INTERVAL_MIN} min (investment timing alerts)")
    print("Press Ctrl+C to exit.")
    print("--------------------------------------------------")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler shutting down...")


if __name__ == "__main__":
    main()
