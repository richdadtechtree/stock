import os
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from notifier import send_telegram_photo

load_dotenv()

PORT = os.getenv("PORT", "8000")
HOST = os.getenv("HOST", "127.0.0.1")

SCREENSHOT_PATH = "static/briefing_screenshot.png"


def capture_and_send():
    """
    Launches a headless browser, captures the dashboard, and sends it via Telegram.
    """
    url = f"http://{HOST}:{PORT}/"
    print(f"Navigating to dashboard at: {url}")

    success = False

    with sync_playwright() as p:
        try:
            # Launch headless browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Set high-DPI viewport for crisp screenshot (TQQQ + 알람 섹션 포함 높이)
            page.set_viewport_size({"width": 1320, "height": 1080})

            # Open dashboard URL
            page.goto(url)

            # Wait for data fetching to complete (skeleton classes removed)
            print("Waiting for dashboard to finish loading data...")
            page.wait_for_selector(".index-card:not(.loading-skeleton)", timeout=15000)

            # Wait for the investment timing section (best-effort)
            try:
                page.wait_for_selector("#alert-container .alert-row", timeout=10000)
            except Exception:
                print("[Warn] Alert status section did not load in time. Capturing anyway.")

            # Sleep slightly to ensure CSS transitions/animations settle
            time.sleep(1.5)

            # Select the main dashboard container and take screenshot of just that element
            dashboard_element = page.locator("#dashboard")
            os.makedirs(os.path.dirname(SCREENSHOT_PATH), exist_ok=True)
            dashboard_element.screenshot(path=SCREENSHOT_PATH)
            print(f"Screenshot successfully saved to {SCREENSHOT_PATH}")

            browser.close()
            success = True
        except Exception as e:
            print(f"[Error] Playwright screenshot failed: {e}")
            if 'browser' in locals():
                browser.close()
            return False

    if success:
        date_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 마감")
        caption = (
            f"📈 *주요 시장 지수 마감 브리핑*\n"
            f"📅 일시: {date_str}\n\n"
            f"코스피, 코스닥, S&P 500, TQQQ 현황과 투자 타이밍 진행 상태를 공유합니다."
        )
        print("Sending photo to Telegram...")
        if send_telegram_photo(SCREENSHOT_PATH, caption):
            print("Telegram briefing message sent successfully!")
            return True

    return False


if __name__ == "__main__":
    capture_and_send()
