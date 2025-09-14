# telegram_notifier.py (抜粋)
import os
import requests

class TelegramNotifier:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send(self, message: str):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"   # ← HTMLモードに
        }
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            print("Telegram送信失敗:", e)
