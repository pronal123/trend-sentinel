import requests
import logging
import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramNotifier:
    def __init__(self, token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.base = f"https://api.telegram.org/bot{self.token}"

    def send(self, text):
        if not self.token or not self.chat_id:
            logging.warning("Telegram config missing; skipping send")
            return
        try:
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            resp = requests.post(f"{self.base}/sendMessage", data=payload, timeout=10)
            if resp.status_code != 200:
                logging.error(f"Telegram send failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logging.error(f"Telegram send exception: {e}")

    def send_trade_summary(self, long_list, short_list, spikes, meta):
        ts = datetime.datetime.now().astimezone().strftime("%Y/%m/%d %H:%M JST")
        title = f"📡 トレンドセンチネル速報（{ts}）\n\n"
        body = ""
        def mk_list(items, label):
            if not items: return f"— {label}: なし\n\n"
            s = f"— {label}:\n"
            for t in items[:10]:
                s += f"{t['symbol']}  | 24h:{t['24h']:+.1f}%  1h:{t['1h']:+.1f}%  vol:{t['vol_pct']:+.0f}%\n  根拠: {t.get('reason','')}\n"
            s += "\n"
            return s

        body += mk_list(long_list, "LONG候補 上位")
        body += mk_list(short_list, "SHORT候補 上位")
        body += mk_list(spikes, "急騰アラート")
        body += f"市場概況: 監視銘柄数 {meta.get('total',0)} / LONG検出 {len(long_list)} / SHORT検出 {len(short_list)} / 急騰 {len(spikes)}\n"
        self.send(title + body)
