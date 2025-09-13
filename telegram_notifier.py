# telegram_notifier.py
import os
from telegram import Bot
from datetime import datetime
import pytz
import logging

class TelegramNotifier:
    def __init__(self):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        self.bot = Bot(token=token) if token else None

    def _format_message(self, long_df, short_df, spike_df, summary):
        if not self.bot: return "Telegram Bot not configured."
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst).strftime('%Y/%m/%d %H:%M JST')
        
        msg = f"📡 *トレンドセンチネル速報（{now}）*\n\n"
        msg += "📈 *LONG候補トップ3*\n"
        if not long_df.empty:
            for _, r in long_df.head(3).iterrows():
                msg += f"- *{r['symbol'].upper()}* (${r['current_price']:.4f})\n  - 24h: *{r['price_change_24h']:.2f}%* | 1h: *{r['price_change_1h']:.2f}%*\n  - _根拠: 価格上昇、強いモメンタム、出来高急増_\n"
        else: msg += "_該当なし_\n"
        
        # ... (SHORT, 急騰アラート, 市場概況も同様に記述)
        
        return msg

    def send_notification(self, *args):
        if not self.bot: return
        message = self._format_message(*args)
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            logging.info("Telegram notification sent.")
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")
    
    # TODO: 日次サマリーのロジックを実装
    def send_daily_summary(self, all_data):
        pass
