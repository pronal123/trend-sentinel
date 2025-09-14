import os
import logging
from flask import Flask, jsonify
from threading import Thread
import schedule, time, asyncio

from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor  # 既存ファイル

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Flask
app = Flask(__name__)

# 初期化
state = StateManager()
data = DataAggregator()
executor = TradingExecutor(state)

# 定期ジョブ
async def run_trading_cycle():
    logging.info("Trading cycle tick.")
    # 本番では AnalysisEngine.run_analysis() を実行してシグナル検出
    # ここではダミーで残高更新
    balance = state.get_balance()
    state.update_balance(balance + 0.0)

def run_scheduler():
    schedule.every(1).minutes.do(lambda: asyncio.run(run_trading_cycle()))
    while True:
        schedule.run_pending()
        time.sleep(1)

Thread(target=run_scheduler, daemon=True).start()

@app.route("/")
def home():
    return "🚀 Trading Bot is running."

@app.route("/status")
def status():
    balance = state.get_balance()
    win_rate = state.get_win_rate()
    positions = state.get_positions()

    # 監視銘柄: ポジションがなければBTC/USDTのみ
    symbols = ["BTC/USDT"] if not positions else ["BTC/USDT"] + list(positions.keys())
    market_data = data.get_market_snapshot(symbols)
    fear_greed = data.fetch_fear_greed_index()

    return jsonify({
        "account": {
            "balance": balance,
            "win_rate": win_rate,
            "positions": positions
        },
        "market": market_data,
        "global": {
            "fear_greed_index": fear_greed
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
