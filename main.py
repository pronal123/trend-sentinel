import os
import logging
import json
import time
import pytz
import schedule
import requests
from datetime import datetime
from flask import Flask, jsonify

from data_aggregator import build_market_snapshot
from state_manager import StateManager

logging.basicConfig(level=logging.INFO)

# 環境変数
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Flask
app = Flask(__name__)
state = StateManager("bot_state.json")

# Telegram送信
def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials not found, skipping message send")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"  # 太字や改行を反映
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            logging.error(f"Telegram send error: {res.text}")
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")

# AIコメント通知用
def format_snapshot_for_telegram(snapshot):
    now = datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y/%m/%d %H:%M")
    msg = f"📡 <b>トレンドセンチネル速報（{now} JST）</b>\n\n"
    for symbol, data in snapshot.items():
        msg += f"<b>{symbol}</b>\n"
        msg += f"💰 価格: {data['last_price']}\n"
        msg += f"🎯 利確: {data['take_profit']} | 🛑 損切: {data['stop_loss']}\n"
        msg += f"<code>{data['comment']}</code>\n\n"
    return msg

# 定期監視タスク
def monitor_cycle():
    logging.info("Running monitor cycle...")
    snapshot = build_market_snapshot(state)
    # 状態保存（バックアップ用途）
    state.save_snapshot(snapshot)
    # Telegram送信
    message = format_snapshot_for_telegram(snapshot)
    send_telegram_message(message)

# Flask API
@app.route("/status", methods=["GET"])
def status():
    snapshot = build_market_snapshot(state)
    return jsonify(snapshot)

# 定期実行スケジュール（6時間ごと）
schedule.every().day.at("02:00").do(monitor_cycle)
schedule.every().day.at("08:00").do(monitor_cycle)
schedule.every().day.at("14:00").do(monitor_cycle)
schedule.every().day.at("20:00").do(monitor_cycle)

# 常駐ループ
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    import threading
    # スケジューラーを別スレッドで起動
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    # Flask起動
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
