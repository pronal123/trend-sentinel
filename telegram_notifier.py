# telegram_notifier.py
import logging
import requests
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_message(self, text: str):
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            requests.post(self.api_url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Failed to send Telegram message: {e}")

    # ---------- entry ----------
    def notify_entry(self, symbol, side, entry_price, size, balance_usd, balance_jpy, entry_count):
        now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            f"📈 <b>新規エントリー</b>\n"
            f"⏰ {now} (JST)\n"
            f"🔹 通貨: {symbol}\n"
            f"📊 サイド: <b>{side}</b>\n"
            f"💵 価格: {entry_price}\n"
            f"📦 サイズ: {size}\n"
            f"💰 残高: ${balance_usd:.2f} / ¥{balance_jpy:,.0f}\n"
            f"📝 通算エントリー回数: {entry_count}"
        )
        self.send_message(msg)

    # ---------- exit ----------
    def notify_exit(self, symbol, side, exit_price, pnl_usd, pnl_jpy, balance_usd, balance_jpy, reason, exit_count):
        now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        emoji = "✅" if pnl_usd >= 0 else "❌"
        msg = (
            f"{emoji} <b>決済</b>\n"
            f"⏰ {now} (JST)\n"
            f"🔹 通貨: {symbol}\n"
            f"📊 サイド: <b>{side}</b>\n"
            f"💵 決済価格: {exit_price}\n"
            f"📈 損益: ${pnl_usd:.2f} / ¥{pnl_jpy:,.0f}\n"
            f"💰 残高: ${balance_usd:.2f} / ¥{balance_jpy:,.0f}\n"
            f"📝 理由: {reason}\n"
            f"📊 通算決済回数: {exit_count}"
        )
        self.send_message(msg)

    # ---------- hourly summary ----------
    def notify_summary(self, balance_usd, balance_jpy, positions, daily_pnl_usd, daily_pnl_jpy, entry_count, exit_count):
        now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        pos_text = "なし"
        if positions:
            pos_text = "\n".join(
                f"{sym}: {p['side']} @ {p['entry_price']}, サイズ={p['size']}"
                for sym, p in positions.items()
            )

        msg = (
            f"⏰ <b>毎時サマリー</b>\n"
            f"{now} (JST)\n\n"
            f"💰 残高: ${balance_usd:.2f} / ¥{balance_jpy:,.0f}\n"
            f"📈 日次損益: ${daily_pnl_usd:.2f} / ¥{daily_pnl_jpy:,.0f}\n"
            f"📊 取引回数: エントリー={entry_count}, 決済={exit_count}\n\n"
            f"📦 保有中ポジション:\n{pos_text}"
        )
        self.send_message(msg)
