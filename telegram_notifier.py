# telegram_notifier.py
import os
import requests
import logging
from datetime import datetime, timezone, timedelta

# Telegram設定（環境変数から読み込み）
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# 日本時間
JST = timezone(timedelta(hours=9))


class TelegramNotifier:
    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID

    def send_html(self, text: str):
        """TelegramにHTML形式で通知"""
        if not self.token or not self.chat_id:
            logging.debug("Telegram not configured.")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error("send_telegram error: %s", e)

    # --- 為替レート取得 (USD/JPY) ---
    def fetch_usd_jpy(self) -> float:
        try:
            url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=USDJPY=X"
            r = requests.get(url, timeout=5)
            data = r.json()
            price = data["quoteResponse"]["result"][0]["regularMarketPrice"]
            return float(price)
        except Exception as e:
            logging.error("USD/JPY取得エラー: %s", e)
            return 150.0  # フォールバック値

    # --- 新規ポジション通知 ---
    def notify_new_entry(self, symbol, side, price, size_usd, tp, sl, comment=""):
        msg = f"<b>📥 新規ポジション</b>\n"
        msg += f"<b>{symbol}</b> {side.upper()} @ <code>{price:.6f}</code>\n"
        msg += f"Size(USDT): <code>{size_usd:.2f}</code>\n"
        msg += f"TP: <code>{tp:.6f}</code> / SL: <code>{sl:.6f}</code>\n"
        if comment:
            msg += f"<pre>{comment}</pre>"
        self.send_html(msg)

    # --- 決済通知 ---
    def notify_exit(self, symbol, reason, exit_price, pnl_usd):
        usd_jpy = self.fetch_usd_jpy()
        pnl_jpy = pnl_usd * usd_jpy

        emoji = "✅" if reason == "TP" else "❌"
        msg = f"<b>{emoji} 決済 ({reason})</b>\n"
        msg += f"<b>{symbol}</b> Exit: <code>{exit_price:.6f}</code>\n"
        msg += f"損益: <code>{pnl_usd:.2f} USD</code> / <code>{pnl_jpy:.0f} JPY</code>"
        self.send_html(msg)

    # --- 毎時サマリー通知 ---
    def notify_summary(self, balance_usd, positions, daily_pnl_usd, entry_count, exit_count):
        usd_jpy = self.fetch_usd_jpy()
        balance_jpy = balance_usd * usd_jpy
        daily_pnl_jpy = daily_pnl_usd * usd_jpy

        now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")

        msg = f"<b>⏰ 毎時サマリー ({now})</b>\n"
        msg += f"残高: <code>{balance_usd:.2f} USD</code> / <code>{balance_jpy:.0f} JPY</code>\n"
        msg += f"今日の損益: <code>{daily_pnl_usd:.2f} USD</code> / <code>{daily_pnl_jpy:.0f} JPY</code>\n"
        msg += f"新規エントリー回数: <code>{entry_count}</code>\n"
        msg += f"決済回数: <code>{exit_count}</code>\n"

        if positions:
            msg += "\n<b>📊 保有ポジション:</b>\n"
            for sym, pos in positions.items():
                msg += f"- {sym} {pos['side']} @ {pos['entry_price']:.4f}\n"
        else:
            msg += "\n保有ポジション: なし"

        self.send_html(msg)
