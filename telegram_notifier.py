# telegram_notifier.py
import os
from telegram import Bot
import logging
from datetime import datetime
import pytz

class TelegramNotifier:
    """
    Telegramへの通知を専門に担当するクラス。
    """
    def __init__(self):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        self.bot = Bot(token=token) if token and self.chat_id else None
        if not self.bot:
            logging.warning("Telegram Bot token or Chat ID not found. Notifications are disabled.")

    def send_new_position_notification(self, position_data):
        """
        新規ポジション獲得時に、詳細な情報をTelegramに通知する。
        """
        if not self.bot: return

        p = position_data
        
        # 利確・損切時の想定残高を計算
        # 簡易計算のため、ここでは手数料を考慮しない
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
        except Exception as e:
            logging.error(f"Failed to send new position notification: {e}")

    # TODO: send_regular_scan_notification, send_daily_summary などの実装
