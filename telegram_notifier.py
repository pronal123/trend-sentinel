import os
import time
import pytz
import requests
import logging
from datetime import datetime
from state_manager import StateManager

# ===== 設定 =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JPY_RATE = 150.0  # 為替レート（ドル円固定 or 別APIで取得してもOK）

# ===== Telegram送信関数 =====
def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            logging.error(f"Telegram送信エラー: {res.text}")
    except Exception as e:
        logging.error(f"Telegram送信失敗: {e}")

# ===== 通知メッセージ生成 =====
def format_usd_jpy(amount):
    return f"{amount:.2f} USDT (≈ {amount * JPY_RATE:.0f} 円)"

def format_datetime(ts=None):
    tz = pytz.timezone("Asia/Tokyo")
    if ts is None:
        dt = datetime.now(tz)
    else:
        dt = datetime.fromtimestamp(ts, tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_entry(event, balance):
    return (
        f"📈【新規エントリー】\n"
        f"銘柄: {event['symbol']}\n"
        f"方向: {event['side'].upper()}\n"
        f"数量: {event['size']}\n"
        f"建値: {event['price']}\n"
        f"時刻: {format_datetime(event['time'])}\n\n"
        f"口座残高: {format_usd_jpy(balance)}"
    )

def format_close(event, balance):
    reason_map = {"tp": "TP到達", "sl": "SL発動"}
    return (
        f"{'✅' if event['pnl'] >= 0 else '❌'}【決済】\n"
        f"銘柄: {event['symbol']}\n"
        f"方向: {event['side'].upper()}\n"
        f"数量: {event['size']}\n"
        f"建値: {event['entry']}\n"
        f"決済値: {event['exit']}\n"
        f"確定損益: {format_usd_jpy(event['pnl'])}\n"
        f"理由: {reason_map.get(event['reason'], '手動/不明')}\n\n"
        f"現在残高: {format_usd_jpy(balance)}"
    )

def format_report(state, balance):
    tz = pytz.timezone("Asia/Tokyo")
    now = datetime.now(tz)
    positions = state.get_all_positions()
    pnl_total = 0.0

    pos_lines = []
    for sym, details in positions.items():
        pnl = details.get("pnl", 0.0)
        pnl_total += pnl
        pos_lines.append(
            f"- {sym} {details['side']} {details['size']} "
            f"建値 {details['entry']} 損益 {format_usd_jpy(pnl)}"
        )

    today_pnl = state.get_today_realized_pnl()
    entry_count, close_count = state.get_today_trade_counts()

    msg = (
        f"🕒【定期レポート】({now.strftime('%Y-%m-%d %H:%M JST')})\n"
        f"口座残高: {format_usd_jpy(balance)}\n\n"
    )
    if pos_lines:
        msg += "保有ポジション:\n" + "\n".join(pos_lines) + "\n\n"
    else:
        msg += "保有ポジション: なし\n\n"

    msg += (
        f"合計含み損益: {format_usd_jpy(pnl_total)}\n\n"
        f"📊 今日の確定損益: {format_usd_jpy(today_pnl)}\n"
        f"🔢 今日の取引回数: エントリー {entry_count}回 / 決済 {close_count}回"
    )
    return msg

# ===== メインループ =====
def run_notifier():
    state = StateManager()
    last_event_id = 0
    last_report_hour = -1

    while True:
        try:
            # 新しいイベントを確認
            events = state.get_trade_events()
            for event in events:
                if event["id"] <= last_event_id:
                    continue

                balance = event.get("balance", 0.0)
                if event["type"] == "entry":
                    send_telegram_message(format_entry(event, balance))
                elif event["type"] == "close":
                    send_telegram_message(format_close(event, balance))

                last_event_id = event["id"]

            # 毎時レポート
            tz = pytz.timezone("Asia/Tokyo")
            now = datetime.now(tz)
            if now.minute == 0 and now.hour != last_report_hour:
                balance = state.get_balance()
                report_msg = format_report(state, balance)
                send_telegram_message(report_msg)
                last_report_hour = now.hour

        except Exception as e:
            logging.error(f"Notifierループエラー: {e}")

        time.sleep(5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_notifier()
