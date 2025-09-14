import os
import threading
import schedule
import time
import logging
from flask import Flask, jsonify, request, render_template

from state_manager import StateManager
from data_aggregator import DataAggregator

# ===============================
# ログ設定
# ===============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===============================
# 初期化
# ===============================
app = Flask(__name__)
state_manager = StateManager()
data_aggregator = DataAggregator()

API_KEY = os.getenv("API_KEY", "changeme")

# ===============================
# Flask エンドポイント
# ===============================
@app.route("/status")
def status():
    """JSON ステータス"""
    key = request.args.get("key")
    if key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify(state_manager.get_status())

@app.route("/status_page")
def status_page():
    """ダッシュボード (HTML + JS)"""
    return render_template("status_page.html")

# ===============================
# 定期トレーディングサイクル
# ===============================
def run_trading_cycle():
    """通常監視・トレードサイクル"""
    logging.info("=== Trading Cycle Start ===")

    # 🔹 データスナップショットを同期取得
    snapshot = data_aggregator.build_market_snapshot(["BTC", "ETH", "SOL", "BNB"])
    logging.info(f"Market snapshot at {snapshot['timestamp']}")

    # 🔹 ダミートレード結果を保存
    last_balance = (
        state_manager.state["balance_history"][-1]["balance"]
        if state_manager.state["balance_history"]
        else 10000
    )
    state_manager.record_trade_result(
        "BTC", "LONG", pnl=5.0, balance=last_balance + 5.0
    )

    logging.info("Cycle finished. State updated.")

def scheduler_thread():
    """スケジューラ実行スレッド"""
    while True:
        schedule.run_pending()
        time.sleep(1)

# ===============================
# メイン処理
# ===============================
if __name__ == "__main__":
    logging.info("Starting bot...")

    # 🔹 1分ごとにサイクル実行
    schedule.every(1).minutes.do(run_trading_cycle)

    # 🔹 バックグラウンドでスケジューラを実行
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()

    # 🔹 Flask サーバー起動
    app.run(host="0.0.0.0", port=5000)

