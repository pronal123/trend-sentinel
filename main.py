import os
import asyncio
import logging
import schedule
import time
from dotenv import load_dotenv
from flask import Flask, request, abort
from threading import Thread
from datetime import datetime
import pytz
import requests

from analysis_engine import AnalysisEngine
from state_manager import StateManager
from trading_executor import TradingExecutor
from data_aggregator import DataAggregator

# ---------------------------------------------------
# 環境変数ロード & ロガー設定
# ---------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Flask アプリ
app = Flask(__name__)

# ---------------------------------------------------
# 初期化
# ---------------------------------------------------
state_manager = StateManager()
data_aggregator = DataAggregator()
analyzer = AnalysisEngine()
executor = TradingExecutor(state_manager)

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 認証キー（内部監視用）
STATUS_AUTH_KEY = os.getenv("STATUS_AUTH_KEY", "changeme")

# ---------------------------------------------------
# ダミーモデル
# ---------------------------------------------------
def load_model():
    logging.info("Dummy model loaded (replace with actual model).")
    return "dummy_model"

model = load_model()

# ---------------------------------------------------
# Telegram 通知関数
# ---------------------------------------------------
def send_telegram_message(html_text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials missing, skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": html_text,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, data=payload, timeout=10)
        if res.status_code != 200:
            logging.error(f"Telegram send error: {res.text}")
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")

def jst_now_str():
    return datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y/%m/%d %H:%M")

# ---------------------------------------------------
# レポート作成
# ---------------------------------------------------
def build_regular_report(long_df, short_df, spike_df, summary):
    balance = executor.get_account_balance_usd()
    win_rate = state_manager.get_win_rate()
    market_snapshot = data_aggregator.build_market_snapshot()

    msg = f"<b>📡 トレンドセンチネル定期レポート（{jst_now_str()} JST）</b>\n\n"
    msg += f"<b>💰 残高</b> : {balance:.2f} USDT\n"
    msg += f"<b>📊 勝率</b> : {win_rate:.1f}%\n"
    msg += f"<b>📈 市場状況</b> : {market_snapshot.get('fear_greed','N/A')}\n\n"

    # LONG 候補
    msg += "<b>🔹 LONG 候補</b>\n"
    if not long_df.empty:
        for _, row in long_df.iterrows():
            msg += f"• <b>{row['symbol']}</b> (+{row['price_change_24h']:.1f}% / 出来高 {row['volume_change_24h']:.0f}%)\n"
            msg += f"  └ 利確: {row.get('take_profit','-')} / 損切: {row.get('stop_loss','-')}\n"
            msg += f"  └ AIコメント: 「買い優勢、モメンタム強」\n"
    else:
        msg += "（該当なし）\n"

    # SHORT 候補
    msg += "\n<b>🔻 SHORT 候補</b>\n"
    if not short_df.empty:
        for _, row in short_df.iterrows():
            msg += f"• <b>{row['symbol']}</b> ({row['price_change_24h']:.1f}% / 出来高 {row['volume_change_24h']:.0f}%)\n"
            msg += f"  └ 利確: {row.get('take_profit','-')} / 損切: {row.get('stop_loss','-')}\n"
            msg += f"  └ AIコメント: 「売り圧力優勢」\n"
    else:
        msg += "（該当なし）\n"

    # Spike 候補
    msg += "\n<b>⚡ 急騰アラート</b>\n"
    if not spike_df.empty:
        for _, row in spike_df.iterrows():
            msg += f"• <b>{row['symbol']}</b> (+{row['price_change_1h']:.1f}% / 15分出来高急増)\n"
    else:
        msg += "（該当なし）\n"

    return msg

def build_signal_alert(row, signal_type):
    msg = f"<b>🚨 シグナル検出（{jst_now_str()} JST）</b>\n\n"
    msg += f"<b>{signal_type}</b> シグナル: <b>{row['symbol']}</b>\n"
    msg += f"24h変動: {row['price_change_24h']:.1f}% / 出来高 {row['volume_change_24h']:.0f}%\n"
    msg += f"利確: {row.get('take_profit','-')} / 損切: {row.get('stop_loss','-')}\n"
    msg += f"AIコメント: 「相場動向に注目」\n"
    return msg

# ---------------------------------------------------
# 非同期トレーディングサイクル
# ---------------------------------------------------
async def run_trading_cycle_async():
    logging.info("--- 🚀 Starting New Intelligent Trading Cycle ---")
    win_rate = state_manager.get_win_rate()
    logging.info(f"Current Bot Win Rate: {win_rate:.2f}%")

    market_data = await data_aggregator.fetch_all()
    if not market_data:
        logging.error("No market data fetched. Skipping cycle.")
        return

    safe_data = data_aggregator.to_dataframe(market_data)
    if safe_data.empty:
        logging.error("Market dataframe is empty. Skipping cycle.")
        return

    long_df, short_df, spike_df, summary = analyzer.run_analysis(safe_data, model)

    # シグナル検出時に即時通知
    if not long_df.empty:
        for _, row in long_df.iterrows():
            send_telegram_message(build_signal_alert(row, "LONG"))
            executor.open_position("LONG", row['symbol'], safe_data, score=80)

    if not short_df.empty:
        for _, row in short_df.iterrows():
            send_telegram_message(build_signal_alert(row, "SHORT"))
            executor.open_position("SHORT", row['symbol'], safe_data, score=80)

    if not spike_df.empty:
        for _, row in spike_df.iterrows():
            send_telegram_message(build_signal_alert(row, "SPIKE"))

    # 定期レポート送信
    report_msg = build_regular_report(long_df, short_df, spike_df, summary)
    send_telegram_message(report_msg)

    # 状態保存
    state_manager.save_state()

# ---------------------------------------------------
# スケジューラ設定
# ---------------------------------------------------
def run_scheduler():
    schedule.every(5).minutes.do(lambda: asyncio.run(run_trading_cycle_async()))
    while True:
        schedule.run_pending()
        time.sleep(1)

# ---------------------------------------------------
# Flask エンドポイント
# ---------------------------------------------------
@app.route("/status")
def status():
    auth = request.headers.get("Authorization")
    if auth != f"Bearer {STATUS_AUTH_KEY}":
        abort(401)
    return {
        "win_rate": state_manager.get_win_rate(),
        "balance": executor.get_account_balance_usd(),
        "positions": state_manager.get_all_active_positions(),
        "market": data_aggregator.build_market_snapshot()
    }

@app.route("/")
def home():
    return "🚀 Intelligent Trading Bot Dashboard (Auth Required for /status)"

# ---------------------------------------------------
# メインエントリーポイント
# ---------------------------------------------------
if __name__ == "__main__":
    logging.info("Initializing Bot...")

    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    logging.info("Scheduler thread started.")
    logging.info("--- Starting BOT in ASYNC Direct Debug Mode ---")

    try:
        asyncio.run(run_trading_cycle_async())
    except Exception as e:
        logging.error(f"Error in initial run: {e}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
