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
from market_data import get_snapshot, load_ath_from_history, get_custom_stocks_snapshot
from trigger_engine import TriggerEngine, format_events, format_custom_events, format_sidecar_events
from notifier import send_telegram_message

load_dotenv()

# Server config
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "127.0.0.1")

# 투자 타이밍 트리거 체크 주기 (분)
ALERT_CHECK_INTERVAL_MIN = int(os.getenv("ALERT_CHECK_INTERVAL_MIN", "10"))

# 마감 브리핑 시각 (한국시각 기준).
# 코스피·코스닥은 15:20~15:30 종가 단일가 매매로 15:30에 종가가 확정되며,
# 그 값이 시세 API로 전파되는 데 몇 분이 걸립니다. 그래서 정각 15:30이 아니라
# 조금 여유를 둔 15:40을 기본값으로 두어 "확정된 종가"를 잡습니다.
BRIEFING_HOUR = int(os.getenv("BRIEFING_HOUR", "15"))
BRIEFING_MINUTE = int(os.getenv("BRIEFING_MINUTE", "40"))

# 스케줄러 기준 시간대. 서버가 UTC 등 다른 시간대에서 돌아도
# 항상 한국시각(장 마감 시각)에 맞춰 실행되도록 명시합니다.
SCHEDULER_TZ = os.getenv("SCHEDULER_TZ", "Asia/Seoul")


def run_server():
    """
    Runs the FastAPI Uvicorn server.
    """
    print(f"Starting FastAPI Web Server at http://{HOST}:{PORT}")
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="warning")


def daily_job():
    """
    Triggered daily at 마감 브리핑 시각 — 대시보드 캡처 후 텔레그램 전송.

    캡처 직전에 캐시를 무시하고 최신 종가를 한 번 새로 받아옵니다.
    이렇게 해두면 뒤이어 대시보드가 읽는 60초 캐시에 방금 확정된 종가가 담겨,
    브리핑 사진이 장중 직전 값이 아니라 실제 마감 수치를 보여줍니다.
    """
    print(f"[{datetime.now()}] Starting scheduled daily briefing capture...")

    # 확정된 마감 종가로 캐시를 강제 갱신 (실패해도 캡처는 진행)
    try:
        snapshot = get_snapshot(use_cache=False)
        if snapshot:
            summary = ", ".join(
                f"{name} {d['current']:,.2f}({d['change_rate']:+.2f}%)"
                for name, d in snapshot.items()
            )
            print(f"[{datetime.now()}] Refreshed closing snapshot: {summary}")
        else:
            print(f"[{datetime.now()}] [Warn] Closing snapshot empty; capturing with existing data.")
        get_custom_stocks_snapshot(use_cache=False)
    except Exception as e:
        print(f"[{datetime.now()}] [Warn] Failed to refresh closing snapshot: {e}")

    success = capture_and_send()
    print(f"[{datetime.now()}] Scheduled job completed. Status: {'SUCCESS' if success else 'FAILED'}")


def alert_job():
    """
    지수 투자 타이밍 트리거 및 관심 종목/ETF 급등락 알림을 체크합니다.
    """
    print(f"[{datetime.now()}] Checking triggers and custom stocks/ETFs...")
    engine = TriggerEngine()
    
    # 1. 지수 투자 타이밍 트리거 체크
    try:
        snapshot = get_snapshot()
        if snapshot:
            # 1.1 투자 타이밍 트리거 체크
            events = engine.check(snapshot)
            if events:
                message = format_events(events)
                sent = send_telegram_message(message)
                print(f"[{datetime.now()}] {len(events)} index trigger(s) fired. Telegram: {'SENT' if sent else 'FAILED'}")
            else:
                print(f"[{datetime.now()}] No new index triggers.")
                
            # 1.2 사이드카 발동 여부 체크
            try:
                sidecar_events = engine.check_sidecars(snapshot)
                if sidecar_events:
                    sidecar_message = format_sidecar_events(sidecar_events)
                    sent = send_telegram_message(sidecar_message)
                    print(f"[{datetime.now()}] {len(sidecar_events)} sidecar trigger(s) fired. Telegram: {'SENT' if sent else 'FAILED'}")
            except Exception as se:
                print(f"[Error] Sidecar check failed: {se}")
        else:
            print("[Warn] Empty market snapshot. Skipping index trigger check.")
    except Exception as e:
        print(f"[Error] Index alert check failed: {e}")
        
    # 2. 관심 종목 및 ETF 급등락 알림 체크
    try:
        custom_snapshot = get_custom_stocks_snapshot()
        if custom_snapshot:
            custom_events = engine.check_custom_stocks(custom_snapshot)
            if custom_events:
                custom_message = format_custom_events(custom_events)
                sent = send_telegram_message(custom_message)
                print(f"[{datetime.now()}] {len(custom_events)} custom stock trigger(s) fired. Telegram: {'SENT' if sent else 'FAILED'}")
            else:
                print(f"[{datetime.now()}] No new custom stock/ETF triggers.")
        else:
            print("[Info] No custom stocks configured or empty snapshot.")
    except Exception as e:
        print(f"[Error] Custom stocks alert check failed: {e}")


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

    # Initialize APScheduler (한국시각 기준으로 고정)
    scheduler = BlockingScheduler(timezone=SCHEDULER_TZ)

    # Schedule job: Monday to Friday 마감 브리핑 캡처 전송 (기본 15:40 KST)
    briefing_label = f"{BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d}"
    scheduler.add_job(
        daily_job,
        'cron',
        day_of_week='mon-fri',
        hour=BRIEFING_HOUR,
        minute=BRIEFING_MINUTE,
        id='daily_briefing',
        name=f'Daily Stock Market Briefing at {briefing_label}'
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
    print(f"Timezone: {SCHEDULER_TZ}")
    print(f"Schedule: Mon-Fri at {briefing_label} (briefing capture)")
    print(f"Schedule: every {ALERT_CHECK_INTERVAL_MIN} min (investment timing alerts)")
    print("Press Ctrl+C to exit.")
    print("--------------------------------------------------")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler shutting down...")


if __name__ == "__main__":
    main()
