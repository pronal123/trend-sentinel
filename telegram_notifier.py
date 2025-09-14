# telegram_notifier.py
import os, logging
from datetime import datetime
import pytz
from telegram import Bot
from telegram.error import TelegramError

class TelegramNotifier:
    def __init__(self):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        self.bot = Bot(token=token) if token and self.chat_id else None
        if not self.bot:
            logging.warning("Telegram Bot not configured. Notifications are disabled.")

    def _send_message(self, message):
        if not self.bot: return
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            return True
        except TelegramError as e:
            logging.error(f"Telegram Error: {e}")
            return False

    def send_new_position_notification(self, p_data):
        profit_on_tp = (p_data['take_profit'] - p_data['entry_price']) * p_data['position_size']
        loss_on_sl = (p_data['stop_loss'] - p_data['entry_price']) * p_data['position_size']
        message = (
            f"✅ *新規ポジション獲得通知*\n\n"
            f"通貨: *{p_data['ticker']}*\n参入価格: *${p_data['entry_price']:,.4f}*\n\n"
            f"--- 資金状況 ---\n総残高: *${p_data['current_balance']:,.2f}*\nポジションサイズ: *{p_data['position_size']:.6f} {p_data['asset']}* (${p_data['trade_amount_usd']:,.2f})\n\n"
            f"--- 出口戦略 ---\n🟢 利確: *${p_data['take_profit']:,.4f}* (利益: *+${profit_on_tp:,.2f}*)\n🔴 損切: *${p_data['stop_loss']:,.4f}* (損失: *-${abs(loss_on_sl):,.2f}*)\n\n"
            f"--- パフォーマンス ---\n現在の勝率: *{p_data['win_rate']:.2f}%*\n\n"
            f"_{p_data['reason']}_"
        )
        if self._send_message(message):
            logging.info(f"Sent new position notification for {p_data['ticker']}.")

    def send_position_status_update(self, active_positions):
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst).strftime('%Y/%m/%d %H:%M JST')
        message = f"🕒 *ポジション状況 定時報告 ({now})*\n\n"
        if not active_positions:
            message += "現在、アクティブなポジションはありません。"
        else:
            # ... (前回と同様のメッセージ整形ロジック)
            pass
        self._send_message(message)

    def send_close_position_notification(self, ticker, reason, result, pnl):
        emoji = "🎉" if result == 'win' else "😥"
        title = "利確" if reason == "TAKE PROFIT" else "損切"
        message = f"{emoji} *ポジション決済通知*\n\n通貨: *{ticker}*\n決済理由: *{title}*\n確定損益: *${pnl:+.2f}*"
        self._send_message(message)

    def send_error_notification(self, error_message):
        message = f"🚨 *BOTエラー通知*\n\n{error_message}"
        self._send_message(message)

    def send_daily_summary(self, win_rate, trade_history):
        # ... (日次サマリーのメッセージ整形と送信)
        pass
