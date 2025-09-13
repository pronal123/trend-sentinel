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
            total_pnl = 0
            for pos in active_positions:
                # ポジションサイズがなければ計算できないためデフォルト値を設定
                position_size = pos.get('position_size', (pos.get('trade_amount_usd', 100) / pos['entry_price']))
                pnl = (pos['current_price'] - pos['entry_price']) * position_size
                total_pnl += pnl
                pnl_percent = (pos['current_price'] / pos['entry_price'] - 1) * 100
                
                status_emoji = "🟢" if pnl >= 0 else "🔴"

                message += (
                    f"{status_emoji} *{pos.get('ticker', 'N/A')}*\n"
                    f"  - 参入価格: ${pos['entry_price']:,.4f}\n"
                    f"  - 現在価格: ${pos['current_price']:,.4f}\n"
                    f"  - 含み損益(P/L): *{pnl_percent:+.2f}%* (${pnl:+.2f})\n\n"
                )
            
            total_status_emoji = "🟢" if total_pnl >= 0 else "🔴"
            message += f"--------------------\n"
            message += f"{total_status_emoji} *合計含み損益: ${total_pnl:+.2f}*"

        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logging.info("Sent hourly position status update.")
        except Exception as e:
            logging.error(f"Failed to send position status update: {e}")
