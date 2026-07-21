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

# Optional executable path override (useful on sandboxes with pre-installed chromium)
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH")


def capture_dashboard(path=SCREENSHOT_PATH):
    """
    대시보드 웹 화면을 사진으로 찍어 path에 저장. 성공 시 True.
    (전송은 하지 않음 — 캡처만)
    """
    url = f"http://{HOST}:{PORT}/"
    print(f"Navigating to dashboard at: {url}")

    with sync_playwright() as p:
        browser = None
        try:
            launch_kwargs = {"headless": True}
            if CHROMIUM_PATH:
                launch_kwargs["executable_path"] = CHROMIUM_PATH
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page()

            # Set high-DPI viewport for crisp screenshot (TQQQ + 알람 섹션 포함 높이)
            page.set_viewport_size({"width": 1320, "height": 1080})
            page.goto(url)

            print("Waiting for dashboard to finish loading data...")
            page.wait_for_selector(".index-card:not(.loading-skeleton)", timeout=15000)

            # Wait for the investment timing section (best-effort)
            try:
                page.wait_for_selector("#alert-container .alert-row", timeout=10000)
            except Exception:
                print("[Warn] Alert status section did not load in time. Capturing anyway.")

            # Wait for the custom stocks section (best-effort)
            try:
                page.wait_for_selector("#custom-stocks-container .alert-row", timeout=10000)
            except Exception:
                print("[Warn] Custom stocks section did not load in time.")

            # Sleep slightly to ensure CSS transitions/animations settle
            time.sleep(1.5)

            dashboard_element = page.locator("#dashboard")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            dashboard_element.screenshot(path=path)
            print(f"Screenshot successfully saved to {path}")
            return True
        except Exception as e:
            print(f"[Error] Playwright screenshot failed: {e}")
            return False
        finally:
            if browser:
                browser.close()


def capture_and_send():
    """
    대시보드를 캡처해서 텔레그램(브리핑 봇)으로 전송. 성공 시 True.
    """
    if not capture_dashboard(SCREENSHOT_PATH):
        return False

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
