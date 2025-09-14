import os
import asyncio
import logging
import schedule
import time
from flask import Flask, jsonify, render_template_string, request
from threading import Thread
from state_manager import StateManager
from data_aggregator import DataAggregator

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

state_manager = StateManager()
data_aggregator = DataAggregator()

# 認証トークン（内部利用用）
API_TOKEN = os.environ.get("API_TOKEN", "secret123")

# ------------------------------------------------
# JSON API
# ------------------------------------------------
@app.route("/status")
def status():
    token = request.args.get("token")
    if token != API_TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    metrics = state_manager.compute_metrics()
    snapshot = data_aggregator.build_market_snapshot()

    return jsonify({
        "balance": state_manager.get_balance(),
        "win_rate": state_manager.get_win_rate(),
        "positions": state_manager.state["positions"],
        "metrics": metrics,
        "equity_curve": state_manager.get_equity_curve(),
        "market_snapshot": snapshot
    })

# ------------------------------------------------
# Webダッシュボード
# ------------------------------------------------
STATUS_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>Status Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
    .panel { background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);}
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    canvas { background: #fff; border-radius: 12px; }
  </style>
</head>
<body>
  <h1>📊 トレードダッシュボード</h1>
  <div class="grid">
    <div class="panel">
      <h2>勝率ゲージ</h2>
      <canvas id="winRateGauge"></canvas>
    </div>
    <div class="panel">
      <h2>統計パネル</h2>
      <ul id="stats"></ul>
    </div>
  </div>
  <div class="panel">
    <h2>資産曲線</h2>
    <canvas id="equityCurve"></canvas>
  </div>
  <div class="panel">
    <h2>ドローダウン曲線</h2>
    <canvas id="ddCurve"></canvas>
  </div>

  <script>
    async function fetchStatus() {
      const res = await fetch("/status?token=secret123");
      return await res.json();
    }

    async function render() {
      const data = await fetchStatus();
      const winRate = data.win_rate || 0;
      const metrics = data.metrics || {};
      const history = data.equity_curve || [];

      // 勝率ゲージ
      new Chart(document.getElementById("winRateGauge"), {
        type: "doughnut",
        data: {
          labels: ["Win", "Loss"],
          datasets: [{
            data: [winRate, 100 - winRate],
            backgroundColor: ["#4caf50", "#ddd"]
          }]
        },
        options: { cutout: "70%", plugins: { legend: { display: false } } }
      });

      // 統計パネル
      document.getElementById("stats").innerHTML = `
        <li><b>残高:</b> ${data.balance.toFixed(2)} USDT</li>
        <li><b>勝率:</b> ${winRate.toFixed(2)}%</li>
        <li><b>PnL:</b> ${metrics.pnl.toFixed(2)}</li>
        <li><b>最大DD:</b> ${metrics.max_drawdown.toFixed(2)}</li>
        <li><b>Sharpe:</b> ${metrics.sharpe_ratio.toFixed(2)}</li>
        <li><b>Profit Factor:</b> ${metrics.profit_factor.toFixed(2)}</li>
      `;

      // 資産曲線
      new Chart(document.getElementById("equityCurve"), {
        type: "line",
        data: {
          labels: history.map((_, i) => i),
          datasets: [{
            label: "Equity",
            data: history,
            borderColor: "#2196f3",
            fill: false
          }]
        },
      });

      // ドローダウン曲線
      let cummax = 0, dd = [];
      history.forEach(v => {
        cummax = Math.max(cummax, v);
        dd.push(v - cummax);
      });
      new Chart(document.getElementById("ddCurve"), {
        type: "line",
        data: {
          labels: history.map((_, i) => i),
          datasets: [{
            label: "Drawdown",
            data: dd,
            borderColor: "#f44336",
            fill: false
          }]
        },
      });
    }

    render();
    setInterval(render, 5000);
  </script>
</body>
</html>
"""

@app.route("/status_page")
def status_page():
    return render_template_string(STATUS_HTML)

# ------------------------------------------------
# スケジューラ
# ------------------------------------------------
async def run_cycle():
    logging.info("Running trading cycle...")
    snapshot = data_aggregator.build_market_snapshot()
    state_manager.save_state()

def run_scheduler():
    schedule.every(1).minutes.do(lambda: asyncio.run(run_cycle()))
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.info("Starting BOT...")
    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
