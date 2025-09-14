import os
import logging
import schedule
import time
from threading import Thread
from flask import Flask, jsonify, render_template_string, request

from state_manager import StateManager
from data_aggregator import DataAggregator

import numpy as np
import datetime
import random

# ---------------------------------------
# ログ設定
# ---------------------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Flask
app = Flask(__name__)

# ---------------------------------------
# 初期化
# ---------------------------------------
state_manager = StateManager()
data_aggregator = DataAggregator()

# 認証（/status用）
API_KEY = os.getenv("STATUS_API_KEY", "changeme")

# ---------------------------------------
# バックテスト（履歴付き）
# ---------------------------------------
def run_backtest():
    np.random.seed(42)
    n_trades = 1000
    returns = np.random.normal(0.001, 0.01, n_trades)

    balance = [10000]
    trades = []
    for i, r in enumerate(returns):
        new_balance = balance[-1] * (1 + r)
        pnl = new_balance - balance[-1]
        trades.append({
            "id": i + 1,
            "symbol": random.choice(["BTC", "ETH", "SOL", "BNB"]),
            "side": "LONG" if r > 0 else "SHORT",
            "pnl": pnl,
            "balance": new_balance,
            "return_pct": r * 100,
            "timestamp": str(datetime.date.today() - datetime.timedelta(days=(n_trades - i)//3)),
        })
        balance.append(new_balance)

    balance = balance[1:]
    win_rate = (returns > 0).mean() * 100
    gross_profit = returns[returns > 0].sum()
    gross_loss = -returns[returns < 0].sum()
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    peak = np.maximum.accumulate(balance)
    dd = (np.array(balance) - peak) / peak
    max_dd = dd.min() * 100

    # JST日次リターン集計（365日分）
    daily_returns = {}
    base_date = datetime.date.today() - datetime.timedelta(days=365)
    for i in range(365):
        date = base_date + datetime.timedelta(days=i)
        pnl = float(np.random.normal(0, 50))  # ダミー損益
        ret_pct = pnl / 10000
        daily_returns[str(date)] = {
            "pnl_usdt": pnl,
            "return_pct": ret_pct,
        }

    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "balance_curve": balance,
        "drawdown_curve": dd.tolist(),
        "daily_returns": daily_returns,
        "trade_history": trades[-1000:],  # 直近1000件
    }

backtest_result = run_backtest()

# ---------------------------------------
# トレードサイクル（同期処理）
# ---------------------------------------
def run_trading_cycle():
    logging.info("=== Trading Cycle Start ===")
    snapshot = data_aggregator.build_market_snapshot(["BTC", "ETH", "SOL", "BNB"])
    logging.info(f"Market snapshot: {snapshot['timestamp']}")

    last_balance = (
        state_manager.state["balance_history"][-1]["balance"]
        if state_manager.state["balance_history"]
        else 10000
    )
    # ダミートレード記録
    state_manager.record_trade_result("BTC", "LONG", pnl=5.0, balance=last_balance + 5.0)

    logging.info("Cycle finished. State updated.")

# ---------------------------------------
# スケジューラスレッド
# ---------------------------------------
def scheduler_thread():
    schedule.every(1).minutes.do(run_trading_cycle)
    while True:
        schedule.run_pending()
        time.sleep(1)

# ---------------------------------------
# APIエンドポイント
# ---------------------------------------
@app.route("/")
def home():
    return "🚀 Trading Bot is running!"

@app.route("/status")
def status():
    key = request.args.get("key")
    if key != API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    snapshot = state_manager.get_state_snapshot()
    snapshot["backtest"] = backtest_result
    return jsonify(snapshot)

@app.route("/status_page")
def status_page():
    return render_template_string(
        DASHBOARD_HTML,
        api_key=API_KEY,
    )

# ---------------------------------------
# HTMLテンプレート（DASHBOARD_HTML）
# ---------------------------------------
DASHBOARD_HTML = """ 
<!DOCTYPE html>
<html>
<head>
  <title>Trading Bot Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Arial; margin:20px; background:#fff; color:#333; }
    .panel { margin:20px 0; }
    .heatmap { display:grid; grid-template-columns: repeat(53, 12px); grid-gap:2px; }
    .cell { width:12px; height:12px; }
    table { border-collapse: collapse; width:100%; font-size:12px; }
    th, td { border:1px solid #ccc; padding:4px; text-align:center; }
    th { background:#eee; }
  </style>
</head>
<body>
  <h1>🚀 Trading Bot Dashboard</h1>
  <h2>リアルタイム統計</h2>
  <div class="panel"><canvas id="winrateGauge"></canvas></div>
  <div class="panel"><h3>資産曲線</h3><canvas id="balanceChart"></canvas></div>
  <div class="panel"><h3>ドローダウン</h3><canvas id="ddChart"></canvas></div>
  <div class="panel"><h3>日次リターン Heatmap</h3><div id="heatmap" class="heatmap"></div></div>
  <h2>📊 バックテスト結果</h2>
  <div id="backtestStats"></div>
  <div class="panel"><h3>資産曲線（Backtest）</h3><canvas id="btBalance"></canvas></div>
  <div class="panel"><h3>DD曲線（Backtest）</h3><canvas id="btDD"></canvas></div>
  <div class="panel"><h3>日次リターン Heatmap（Backtest, 365日）</h3><div id="btHeatmap" class="heatmap"></div></div>
  <h2>📜 バックテスト取引履歴（直近1000件）</h2>
  <table id="tradeTable">
    <thead>
      <tr><th>ID</th><th>Symbol</th><th>Side</th><th>PnL (USDT)</th><th>Return %</th><th>Balance</th><th>Date</th></tr>
    </thead>
    <tbody></tbody>
  </table>
<script>
// ... (JS は省略、前バージョンのまま)
</script>
</body>
</html>
"""

# ---------------------------------------
# メイン
# ---------------------------------------
if __name__ == "__main__":
    logging.info("Starting bot...")
    t = Thread(target=scheduler_thread, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
