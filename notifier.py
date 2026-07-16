"""
텔레그램 알림 전송 모듈 (텍스트 메시지 / 사진 공용)
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# 브리핑 봇(봇 1) 전용 설정.
# 서버에 이미 다른 용도의 TELEGRAM_BOT_TOKEN 이 있을 수 있으므로,
# 이 프로그램 전용으로 BRIEFING_BOT_TOKEN / BRIEFING_CHAT_ID 를 먼저 사용하고
# 없으면 기존 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 로 자동 대체(하위 호환).
BOT_TOKEN = os.getenv("BRIEFING_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("BRIEFING_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(text, parse_mode="Markdown"):
    """텔레그램 텍스트 메시지 전송. 성공 시 True."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[Error] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env.")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
        })
        response.raise_for_status()
        res_data = response.json()
        if res_data.get("ok"):
            return True
        print(f"Telegram returned error: {res_data}")
    except Exception as e:
        print(f"[Error] Failed to send Telegram message: {e}")
    return False


def send_telegram_photo(photo_path, caption="", parse_mode="Markdown"):
    """텔레그램 사진 전송. 성공 시 True."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[Error] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env.")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo:
            response = requests.post(url, data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "parse_mode": parse_mode,
            }, files={"photo": photo})
        response.raise_for_status()
        res_data = response.json()
        if res_data.get("ok"):
            return True
        print(f"Telegram returned error: {res_data}")
    except Exception as e:
        print(f"[Error] Failed to send photo via Telegram: {e}")
    return False
