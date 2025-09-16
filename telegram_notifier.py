import os
import time
import threading
import schedule
import requests
import ccxt
from datetime import datetime, timedelta, timezone

# ==================
# 基本設定
# ==================
JST = timezone(timedelta(hours=9))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bitget = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY"),
    "secret": os.getenv("BITGET_API_SECRET"),
    "password": os.getenv("BITGET_API_PASSWORD"),
    "enableRateLimit": True,
})

# ==================
# 日次損益管理
# ==================
class DailyPnLTracker:
    def __init__(self):
        self.current_date = datetime.now(JST).date()
        self.realized_pnl_usd = 0.0

    def reset(self):
        """毎日00:00 JSTにリセット"""
        self.current_date = datetime.now(JST).date()
        self.realized_pnl_usd = 0.0
        send_message(f"🌀 日次損益リセット: {self.current_date}")

    def add_realized_pnl(self, pnl_usd: float):
        """決済時に確定損益を加算"""
        self.realized_pnl_usd += pnl_usd

    def get_realized_pnl(self):
        return self.realized_pnl_usd


pnl_tracker = DailyPnLTracker()

# ==================
# 為替レート取得 (USD/JPY)
# ==================
def get_usd_jpy():
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=USDJPY=X"
        r = requests.get(url, timeout=5).json()
        return float(r["quoteResponse"]["result"][0]["regularMarketPrice"])
    except Exception:
        return None

# ==================
# Telegram送信関数
# ==================
def send_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[ERROR] Telegram送信失敗: {e}")

# ==================
# 残高/ポジション取得
# ==================
def get_account_status():
    balance = bitget.fetch_balance()
    positions = bitget.fetch_positions()

    usdt_balance = balance["total"]["USDT"]

    unrealized_pnl = 0.0
    pos_list = []
    for pos in positions:
        if float(pos["contracts"]) > 0:
            symbol = pos["symbol"]
            entry = float(pos["entryPrice"])
            upnl = float(pos["unrealizedPnl"])
            unrealized_pnl += upnl
            pos_list.append(f"{symbol} | EP: {entry:.2f} | PnL: {upnl:+.2f} USDT")

    return usdt_balance, unrealized_pnl, pos_list

# ==================
# 通知処理
# ==================
def notify_summary():
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    balance, unrealized, pos_list = get_account_status()
    realized = pnl_tracker.get_realized_pnl()
    total_pnl = realized + unrealized

    usd_jpy = get_usd_jpy()
    jpy_text = ""
    if usd_jpy:
        balance_jpy = balance * usd_jpy
        realized_jpy = realized * usd_jpy
        unrealized_jpy = unrealized * usd_jpy
        total_jpy = total_pnl * usd_jpy
        jpy_text = f"""
💴 JPY換算 (USDJPY={usd_jpy:.2f}):
　- 残高: {balance_jpy:,.0f} 円
　- 確定: {realized_jpy:+,.0f} 円
　- 含み: {unrealized_jpy:+,.0f} 円
　- 合計: {total_jpy:+,.0f} 円
"""

    msg = f"""
📊 サマリー通知
⏰ 現在時刻: {now}

💰 残高: {balance:.2f} USDT
📈 日次損益:
　- 確定: {realized:+.2f} USDT
　- 含み: {unrealized:+.2f} USDT
　- 合計: {total_pnl:+.2f} USDT
{jpy_text}
📋 ポジション一覧:
""" + ("\n".join(pos_list) if pos_list else "なし")

    send_message(msg)


def notify_new_entry(symbol, entry_price, size):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    balance, unrealized, _ = get_account_status()
    usd_jpy = get_usd_jpy()

    jpy_text = ""
    if usd_jpy:
        balance_jpy = balance * usd_jpy
        jpy_text = f"💴 残高: {balance_jpy:,.0f} 円 (USDJPY={usd_jpy:.2f})"

    msg = f"""
🟢 新規エントリー
⏰ {now}

銘柄: {symbol}
エントリー価格: {entry_price:.2f}
サイズ: {size}

💰 残高: {balance:.2f} USDT
{jpy_text}
"""
    send_message(msg)


def notify_exit(symbol, exit_price, pnl_usd):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    pnl_tracker.add_realized_pnl(pnl_usd)
    balance, unrealized, _ = get_account_status()
    usd_jpy = get_usd_jpy()

    jpy_text = ""
    if usd_jpy:
        balance_jpy = balance * usd_jpy
        pnl_jpy = pnl_usd * usd_jpy
        realized_jpy = pnl_tracker.get_realized_pnl() * usd_jpy
        jpy_text = f"""
💴 JPY換算 (USDJPY={usd_jpy:.2f}):
　- 確定損益: {pnl_jpy:+,.0f} 円
　- 累積損益: {realized_jpy:+,.0f} 円
　- 残高: {balance_jpy:,.0f} 円
"""

    msg = f"""
🔴 決済
⏰ {now}

銘柄: {symbol}
決済価格: {exit_price:.2f}
確定損益: {pnl_usd:+.2f} USDT

💰 残高: {balance:.2f} USDT
📈 日次累積損益: {pnl_tracker.get_realized_pnl():+.2f} USDT
{jpy_text}
"""
    send_message(msg)

# ==================
# スケジューラ
# ==================
def scheduler_loop():
    # 毎時サマリー
    schedule.every().hour.at(":00").do(notify_summary)
    # 毎日00:00 JSTにリセット
    schedule.every().day.at("00:00").do(pnl_tracker.reset)

    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=scheduler_loop, daemon=True).start()
