import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# Load env variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PORT = os.getenv("PORT", "8000")
HOST = os.getenv("HOST", "127.0.0.1")

SCREENSHOT_PATH = "static/briefing_screenshot.png"

def capture_and_send():
    """
    Launches a headless browser, captures the dashboard, and sends it via Telegram.
    """
    if not BOT_TOKEN or not CHAT_ID:
        print("[Error] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env.")
        return False

    url = f"http://{HOST}:{PORT}/"
    print(f"Navigating to dashboard at: {url}")

    success = False
    
    with sync_playwright() as p:
        try:
            # Launch headless browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Set high-DPI viewport for crisp screenshot
            page.set_viewport_size({"width": 1100, "height": 700})
            
            # Open dashboard URL
            page.goto(url)
            
            # Wait for data fetching to complete (skeleton classes removed)
            print("Waiting for dashboard to finish loading data...")
            page.wait_for_selector(".index-card:not(.loading-skeleton)", timeout=15000)
            
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
        # Send screenshot to Telegram
        send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        date_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 마감")
        caption = f"📈 *주요 시장 지수 마감 브리핑*\n📅 일시: {date_str}\n\n오늘 장마감 시점의 코스피, 코스닥, S&P 500 현황을 공유합니다."
        
        try:
            with open(SCREENSHOT_PATH, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': CHAT_ID,
                    'caption': caption,
                    'parse_mode': 'Markdown'
                }
                print("Sending photo to Telegram...")
                response = requests.post(send_url, data=data, files=files)
                response.raise_for_status()
                
                res_data = response.json()
                if res_data.get("ok"):
                    print("Telegram briefing message sent successfully!")
                    return True
                else:
                    print(f"Telegram returned error: {res_data}")
        except Exception as e:
            print(f"[Error] Failed to send photo via Telegram: {e}")
            
    return False

if __name__ == "__main__":
    capture_and_send()
