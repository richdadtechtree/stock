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

load_dotenv()

# Server config
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "127.0.0.1")

def run_server():
    """
    Runs the FastAPI Uvicorn server.
    """
    print(f"Starting FastAPI Web Server at http://{HOST}:{PORT}")
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="warning")

def daily_job():
    """
    Triggered daily at 15:30.
    """
    print(f"[{datetime.now()}] Starting scheduled daily briefing capture...")
    success = capture_and_send()
    print(f"[{datetime.now()}] Scheduled job completed. Status: {'SUCCESS' if success else 'FAILED'}")

def main():
    parser = argparse.ArgumentParser(description="Stock Briefing Bot Scheduler & Server")
    parser.add_argument("--test", action="store_true", help="Run the capture and send function immediately and exit")
    args = parser.parse_args()

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

    # Initialize APScheduler
    scheduler = BlockingScheduler()
    
    # Schedule job: Monday to Friday at 15:30
    scheduler.add_job(
        daily_job,
        'cron',
        day_of_week='mon-fri',
        hour=15,
        minute=30,
        id='daily_briefing',
        name='Daily Stock Market Briefing at 15:30'
    )
    
    print("--------------------------------------------------")
    print("Stock Briefing Scheduler is now running.")
    print("Schedule: Mon-Fri at 15:30 KST")
    print("Press Ctrl+C to exit.")
    print("--------------------------------------------------")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler shutting down...")

if __name__ == "__main__":
    main()
