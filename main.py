import os
import asyncio
import logging
import schedule
import time
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

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
state = StateManager()   # ✅ グローバルでエクスポートされる
data_aggregator = DataAggregator()
analyzer = AnalysisEngine()
executor = TradingExecutor(state)

# ---------------------------------------------------
# モデル読み込み（仮実装: 後で差し替え可）
# ---------------------------------------------------
def load_model():
    logging.info("Dummy model loaded (replace with actual model).")
    return "dummy_model"

model = load_model()

# ---------------------------------------------------
# 非同期トレーディングサイクル
# ---------------------------------------------------
async def run_trading_cycle_async():
    logging.info("--- 🚀 Starting New Intelligent Trading Cycle ---")
    win_rate = state.get_win_rate()
    logging.info(f"Current Bot Win Rate: {win_rate:.2f}%")

    # 市場データ取得
    market_data = await data_aggregator.fetch_all()
    if not market_data:
        logging.error("No market data fetched. Skipping cycle.")
        return

    safe_data = data_aggregator.to_dataframe(market_data)
    if safe_data.empty:
        logging.error("Market dataframe is empty. Skipping cycle.")
        return

    # ✅ model を渡して実行
    long_df, short_df, spike_df, summary = analyzer.run_analysis(safe_data, model)

    logging.info("All technical indicators calculated.")

    # ロングシグナル処理
    if not long_df.empty:
        for _, row in long_df.iterrows():
            logging.info(f"📈 LONG Signal detected: {row['symbol']}")
            executor.open_position("LONG", row['symbol'], safe_data, score=80)

    # ショートシグナル処理
    if not short_df.empty:
        for _, row in short_df.iterrows():
            logging.info(f"📉 SHORT Signal detected: {row['symbol']}")
            executor.open_position("SHORT", row['symbol'], safe_data, score=80)

    # スパイク検出処理
    if not spike_df.empty:
        for _, row in spike_df.iterrows():
            logging.info(f"⚡ Spike detected: {row['symbol']} - Volume Surge")

    # サマリー出力
    logging.info(f"Summary: {summary}")

    # 状態保存
    state.save_state()

# ---------------------------------------------------
# スケジューラ設定
# ---------------------------------------------------
def run_scheduler():
    schedule.every(1).minutes.do(lambda: asyncio.run(run_trading_cycle_async()))
    while True:
        schedule.run_pending()
        time.sleep(1)

# ---------------------------------------------------
# Flask エンドポイント
# ---------------------------------------------------
@app.route("/")
def home():
    return "🚀 Intelligent Trading Bot is running!"

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
