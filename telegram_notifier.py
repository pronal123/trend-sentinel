# telegram_notifier.py
import os
import logging
from datetime import datetime
import pytz
from telegram import Bot
from telegram.error import TelegramError # <--- ★★★ インポートをこれだけに修正 ★★★

class TelegramNotifier:
    """
    Telegramへの通知を専門に担当するクラス。
    最新のライブラリバージョンに対応したエラーハンドリングを含む。
    """
    def __init__(self):
        """
        コンストラクタ。環境変数から認証情報を読み込み、BOTを初期化する。
        """
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID')

        if token:
            logging.info(f"✅ Telegram Token loaded successfully (starts with: {token[:10]}...).")
        else:
            logging.error("❌ FATAL: TELEGRAM_BOT_TOKEN environment variable NOT FOUND.")
        
        if self.chat_id:
            logging.info(f"✅ Telegram Chat ID loaded: {self.chat_id}")
        else:
            logging.error("❌ FATAL: TELEGRAM_CHAT_ID environment variable NOT FOUND.")

        self.bot = Bot(token=token) if token and self.chat_id else None
        if not self.bot:
            logging.warning("Telegram Bot is not configured. Notifications will be disabled.")

    def send_new_position_notification(self, position_data):
        """
        新規ポジション獲得時に、詳細な情報をTelegramに通知する。
        """
        if not self.bot: return

        # ... (メッセージを整形する部分は変更なし)
        p = position_data
        profit_on_tp = (p['take_profit'] - p['entry_price']) * p['position_size']
        # ... (以下、メッセージ作成ロジック)
        message = f"✅ *新規ポジション獲得通知*\n\n通貨: *{p['ticker']}*\n..."

        # --- ▼▼▼ エラーハンドリングを修正 ▼▼▼ ---
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logging.info(f"Sent new position notification for {p['ticker']}.")
        except TelegramError as e:
            # 親となるTelegramErrorをキャッチし、エラーメッセージの内容で判断する
            if "Unauthorized" in str(e):
                logging.error("Telegram Error: Authentication failed. The TELEGRAM_BOT_TOKEN is likely incorrect.")
            elif "Chat not found" in str(e):
                logging.error("Telegram Error: Chat not found. The TELEGRAM_CHAT_ID is incorrect or the bot isn't in the chat.")
            else:
                logging.error(f"An unexpected Telegram error occurred: {e}")
        except Exception as e:
            logging.error(f"An unexpected non-Telegram error occurred while sending notification: {e}")
        # --- ▲▲▲ ここまで ▲▲▲ ---


    def send_position_status_update(self, active_positions):
        """
        1時間ごとに現在のポジション状況を通知する。
        """
        if not self.bot: return

        # ... (メッセージを整形する部分は変更なし)
        message = "🕒 *ポジション状況 定時報告...*"

        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logging.info("Sent hourly position status update.")
        except TelegramError as e:
            logging.error(f"Failed to send position status update due to Telegram error: {e}")
        except Exception as e:
            logging.error(f"Failed to send position status update due to unexpected error: {e}")
