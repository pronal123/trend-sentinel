import os
import logging
import time
import threading
import pytz
import schedule
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request, Response
from functools import wraps

from data_aggregator import build_market_snapshot
from state_manager import StateManager

logging.basicConfig(level=logging.INFO)

# Flask
app = Flask(__name__)
state = StateManager("bot_state.json")

# ---------------------------------------------------
# BASIC 認証
# ---------------------------------------------------
USER = os.getenv("DASHBOARD_USER", "admin")
PASS = os.getenv("DASHBOARD_PASS", "password")

def check_auth(username, password):
    return username == USER and password == PASS

def authenticate():
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": "Basic realm='Login Required'"}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# ---------------------------------------------------
# 定期タスク：6時間ごとに分析
# ---------------------------------------------------
def monitor_cycle():
    snapshot = build_market_snapshot(state)
    state.save_snapshot(snapshot)
    logging.info("✅ Snapshot updated (scheduled).")

schedule.every().day.at("02:00").do(monitor_cycle)
schedule.every().day.at("08:00").do(monitor_cycle)
schedule.every().day.at("14:00").do(monitor_cycle)
schedule.every().day.at("20:00").do(monitor_cycle)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

# ---------------------------------------------------
# API: JSON形式で最新の市場状況
# ---------------------------------------------------
@app.route("/status")
def status():
    snapshot = build_market_snapshot(state)
    return jsonify(snapshot)

# ---------------------------------------------------
# Webフロント: 内部利用専用ダッシュボード
# ---------------------------------------------------
@app.route("/")
@requires_auth
def dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Trend Sentinel Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background: #fff; color: #222; }
            .container { max-width: 1200px; margin: auto; padding: 20px; }
            h1 { text-align: center; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            .card { background: #f9f9f9; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            canvas { width: 100% !important; height: 300px !important; }
            pre { background: #eee; padding: 10px; border-radius: 5px; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📡 Trend Sentinel Dashboard</h1>
            <div class="grid">
                <div class="card">
                    <h2>価格推移</h2>
                    <canvas id="priceChart"></canvas>
                </div>
                <div class="card">
                    <h2>勝率推移</h2>
                    <canvas id="winRateChart"></canvas>
                </div>
            </div>
            <div class="grid">
                <div class="card">
                    <h2>市場状況</h2>
                    <div id="market"></div>
                </div>
                <div class="card">
                    <h2>AIコメント</h2>
                    <pre id="comments"></pre>
                </div>
            </div>
        </div>

        <script>
        const priceCtx = document.getElementById('priceChart').getContext('2d');
        const winCtx = document.getElementById('winRateChart').getContext('2d');

        let priceChart = new Chart(priceCtx, {
            type: 'line',
            data: { labels: [], datasets: [{ label: 'BTC Price', data: [], borderColor: 'blue' }] },
            options: { responsive: true, animation: false }
        });

        let winChart = new Chart(winCtx, {
            type: 'line',
            data: { labels: [], datasets: [{ label: 'Win Rate (%)', data: [], borderColor: 'green' }] },
            options: { responsive: true, animation: false }
        });

        async function fetchStatus() {
            const res = await fetch('/status');
            const data = await res.json();

            // BTC価格を取得
            const btc = data['BTC'] || {};
            const price = btc.last_price || 0;
            const now = new Date().toLocaleTimeString();

            // price chart 更新
            priceChart.data.labels.push(now);
            priceChart.data.datasets[0].data.push(price);
            if (priceChart.data.labels.length > 60) {
                priceChart.data.labels.shift();
                priceChart.data.datasets[0].data.shift();
            }
            priceChart.update();

            // 勝率履歴
            const history = data['meta']?.win_rate_history || [];
            winChart.data.labels = history.map((h,i)=>i);
            winChart.data.datasets[0].data = history;
            winChart.update();

            // 市場状況
            document.getElementById("market").innerText = JSON.stringify(data['meta'], null, 2);

            // コメント
            let comments = "";
            for (const [sym, obj] of Object.entries(data)) {
                if (sym === "meta") continue;
                comments += sym + "\\n" + (obj.comment || "") + "\\n\\n";
            }
            document.getElementById("comments").innerText = comments;
        }

        setInterval(fetchStatus, 1000);
        fetchStatus();
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

# ---------------------------------------------------
if __name__ == "__main__":
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
