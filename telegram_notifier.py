# telegram_notifier.py
import os
from telegram import Bot
from telegram.error import Unauthorized, BadRequest
import logging
from datetime import datetime
import pytz

class TelegramNotifier:
    """
    Telegramへの通知を専門に担当するクラス。
    環境変数の読み込みチェック機能を含む。
    """
    def __init__(self):
        """
        コンストラクタ。環境変数から認証情報を読み込み、BOTを初期化する。
        """
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID')

        # --- ▼▼▼ 環境変数読み込みチェック用のログ ▼▼▼ ---
        if token:
            # トークンの一部だけをログに出力して、読み込まれていることを確認
            logging.info(f"✅ Telegram Token loaded successfully (starts with: {token[:10]}...).")
        else:
            logging.error("❌ FATAL: TELEGRAM_BOT_TOKEN environment variable NOT FOUND.")
        
        if self.chat_id:
            logging.info(f"✅ Telegram Chat ID loaded: {self.chat_id}")
        else:
            logging.error("❌ FATAL: TELEGRAM_CHAT_ID environment variable NOT FOUND.")
        # --- ▲▲▲ ここまで ▲▲▲ ---

        self.bot = Bot(token=token) if token and self.chat_id else None
        if not self.bot:
            logging.warning("Telegram Bot is not configured due to missing credentials. Notifications will be disabled.")

    def send_new_position_notification(self, position_data):
        """
        新規ポジション獲得時に、詳細な情報をTelegramに通知する。
        """
        if not self.bot: return

        p = position_data
        
        profit_on_tp = (p['take_profit'] - p['entry_price']) * p['position_size']
        loss_on_sl = (p['stop_loss'] - p['entry_price']) * p['position_size']
        balance_at_tp = p['current_balance'] + profit_on_tp
        balance_at_sl = p['current_balance'] + loss_on_sl

        message = (
            f"✅ *新規ポジション獲得通知*\n\n"
            f"通貨: *{p['ticker']}*\n"
            f"参入価格: *${p['entry_price']:,.4f}*\n\n"
            f"--- 資金状況 ---\n"
            f"現在の総残高: *${p['current_balance']:,.2f}*\n"
            f"ポジションサイズ: *{p['position_size']:.6f} {p['asset']}* (${p['trade_amount_usd']:,.2f})\n\n"
            f"--- 出口戦略 (損小利大) ---\n"
            f"🟢 利確位置: *${p['take_profit']:,.4f}* (想定利益: *+${profit_on_tp:,.2f}*)\n"
            f"   (利確時残高: *${balance_at_tp:,.2f}*)\n"
            f"🔴 損切位置: *${p['stop_loss']:,.4f}* (想定損失: *-${abs(loss_on_sl):,.2f}*)\n"
            f"   (損切時残高: *${balance_at_sl:,.2f}*)\n\n"
            f"--- パフォーマンス ---\n"
            f"現在の勝率: *{p['win_rate']:.2f}%*\n\n"
            f"_{p['reason']}_"
        )
        
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logging.info(f"Sent new position notification for {p['ticker']}.")
        except Unauthorized:
            logging.error("Telegram Error: Authentication failed. The TELEGRAM_BOT_TOKEN is likely incorrect.")
        except BadRequest as e:
            if "Chat not found" in str(e):
                logging.error("Telegram Error: Chat not found. The TELEGRAM_CHAT_ID is incorrect or the bot isn't in the chat.")
            else:
                logging.error(f"Telegram Error: Bad request. Details: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while sending notification: {e}")

    def send_position_status_update(self, active_positions):
        """
        1時間ごとに現在のポジション状況を通知する。
        """
        if not self.bot: return

        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst).strftime('%Y/%m/%d %H:%M JST')
        
        message = f"🕒 *ポジション状況 定時報告 ({now})*\n\n"

        if not active_positions:
            message += "現在、アクティブなポジションはありません。"
        else:
            # ... (メッセージ整形ロジックは前回と同様)
            pass

        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logging.info("Sent hourly position status update.")
        except Exception as e:
            logging.error(f"Failed to send position status update: {e}")
