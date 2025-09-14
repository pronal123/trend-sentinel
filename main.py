import os
import asyncio
import logging
import schedule
import time
from threading import Thread
from flask import Flask, jsonify, render_template_string, request

from state_manager import StateManager
from data_aggregator import DataAggregator

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
# トレードサイクル
# ---------------------------------------
async def run_trading_cycle():
    logging.info("=== Trading Cycle Start ===")

    # ダミーロジック: BTC価格のみ取得
    snapshot = await data_aggregator.build_market_snapshot(["BTC", "ETH", "SOL", "BNB"])

    logging.info(f"Market snapshot: {snapshot['timestamp']}")

    # 状態保存（残高更新のダミー）
    last_balance = (
        state_manager.state["balance_history"][-1]["balance"]
        if state_manager.state["balance_history"]
        else 10000
    )
    state_manager.record_trade_result("BTC", "win", pnl=5.0, balance=last_balance + 5.0)

    logging.info("Cycle finished. State updated.")


def scheduler_thread():
    schedule.every(1).minutes.do(lambda: asyncio.run(run_trading_cycle()))
    while True:
        schedule.run_pending()
        time.sleep(1)


# ---------------------------------------
# APIエンドポイント
# ---------------------------------------
@app.route("/status")
def status():
    key = request.args.get("key")
    if key != API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    return jsonify(state_manager.get_state_snapshot())


@app.route("/status_page")
def status_page():
    # HTML+JS ダッシュボード
    return render_template_string(
        DASHBOARD_HTML,
        api_key=API_KEY,
    )


# ---------------------------------------
# HTMLテンプレート
# ---------------------------------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Trading Bot Status</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
      body { font-family: Arial; margin:20px; background:#fff; color:#333; }
      .panel { margin:20px 0; }
    </style>
</head>
<body>
  <h1>🚀 Trading Bot Dashboard</h1>

  <div class="panel">
    <canvas id="winrateGauge" width="200" height="200"></canvas>
  </div>

  <div class="panel">
    <h2>資産曲線</h2>
    <canvas id="balanceChart"></canvas>
  </div>

  <div class="panel">
    <h2>ドローダウン</h2>
    <canvas id="ddChart"></canvas>
  </div>

  <div class="panel">
    <h2>日次リターン Heatmap</h2>
    <div id="heatmap"></div>
  </div>

<script>
const API_KEY = "{{ api_key }}";

async function fetchStatus(){
  const res = await fetch(`/status?key=${API_KEY}`);
  return res.json();
}

function renderWinRate(winRate){
  new Chart(document.getElementById("winrateGauge"), {
    type: 'doughnut',
    data: {
      labels: ["Win", "Loss"],
      datasets: [{
        data: [winRate, 100-winRate],
        backgroundColor: ["#4caf50","#e0e0e0"]
      }]
    },
    options: { cutout: "80%", plugins:{legend:{display:false}} }
  });
}

function renderBalance(history){
  const ctx = document.getElementById("balanceChart");
  new Chart(ctx,{
    type:'line',
    data:{
      labels: history.map(x=>x.timestamp),
      datasets:[{label:"Balance", data: history.map(x=>x.balance), borderColor:"#2196f3", fill:false}]
    }
  });
}

function renderDD(history){
  if(history.length==0) return;
  let peak = history[0].balance;
  let dd = history.map(h=>{
    peak = Math.max(peak, h.balance);
    return 100*(h.balance-peak)/peak;
  });
  const ctx = document.getElementById("ddChart");
  new Chart(ctx,{
    type:'line',
    data:{
      labels: history.map(x=>x.timestamp),
      datasets:[{label:"Drawdown %", data: dd, borderColor:"#f44336", fill:false}]
    }
  });
}

function renderHeatmap(daily){
  let html = "<table border=1><tr><th>Date</th><th>PnL(USDT)</th><th>Return %</th></tr>";
  for(const [date,vals] of Object.entries(daily)){
    const color = vals.pnl_usdt>=0 ? "#c8e6c9" : "#ffcdd2";
    html += `<tr style="background:${color}"><td>${date}</td><td>${vals.pnl_usdt.toFixed(2)}</td><td>${(vals.return_pct*100).toFixed(2)}%</td></tr>`;
  }
  html+="</table>";
  document.getElementById("heatmap").innerHTML=html;
}

async function update(){
  const data = await fetchStatus();
  renderWinRate(data.win_rate);
  renderBalance(data.balance_history);
  renderDD(data.balance_history);
  renderHeatmap(data.daily_returns);
}
update();
setInterval(update, 60000);
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
