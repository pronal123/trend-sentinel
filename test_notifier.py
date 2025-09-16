import os
import ccxt
import requests
from datetime import datetime, timezone, timedelta

# ==== 環境変数 ====
BITGET_API_KEY = os.getenv("BITGET_API_KEY")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET")
BITGET_API_PASSWORD = os.getenv("BITGET_API_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==== Bitget 初期化 ====
exchange = ccxt.bitget({
    "apiKey": BITGET_API_KEY,
    "secret": BITGET_API_SECRET,
    "password": BITGET_API_PASSWORD,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})

# ==== データ取得 ====
balance = exchange.fetch_balance()
positions = exchange.fetch_positions()

# ==== Telegram 送信関数 ====
def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    r = requests.post(url, json=payload)
    return r.json()

# ==== メッセージ作成 ====
jst = timezone(timedelta(hours=9))
now = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S JST")

msg = f"✅ テスト通知 ({now})\n\n"
msg += f"残高(USDT): {balance['total'].get('USDT', 'N/A')}\n\n"

if positions:
    msg += "📊 現在のポジション:\n"
    for p in positions:
        symbol = p.get("symbol")
        side = p.get("side")
        size = p.get("contracts", 0)
        upnl = p.get("unrealizedPnl", 0)
        msg += f"- {symbol} {side} {size}枚 / 含み損益: {upnl:.2f} USDT\n"
else:
    msg += "📊 現在ポジションなし\n"

# ==== 送信 ====
result = send_telegram_message(msg)
print("送信結果:", result)
