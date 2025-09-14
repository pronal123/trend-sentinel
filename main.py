# main.py
import os
import asyncio
import logging
from threading import Thread
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request

import time

# local modules
from data_aggregator import DataAggregator
from state_manager import StateManager

# optional: if your project has TradingExecutor/AnalysisEngine, import them and wire in.
# from trading_executor import TradingExecutor
# from analysis_engine import AnalysisEngine

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=None)

# global state (debug_runner or other modules may import state from main)
state = StateManager()
data_agg = DataAggregator()

# placeholder executor/analyzer if you have real ones, plug them here
# executor = TradingExecutor(state)
# analyzer = AnalysisEngine()
# For this implementation we'll emulate executor methods we need:
class DummyExecutor:
    def __init__(self, state):
        self.state = state

    def get_account_balance_usd(self):
        # replace with real exchange call when available
        # If positions exist, compute dummy balance or return default
        return 10000.0

executor = DummyExecutor(state)

# a minimal analyzer stub that returns summary counts (could be replaced)
class DummyAnalyzer:
    def run_analysis(self, df, model=None):
        # returns long_df, short_df, spike_df, summary
        # We'll return empty frames and a small summary placeholder
        import pandas as pd
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {
            "long_count": 0, "short_count": 0, "spike_count": 0, "trend": "neutral", "volatility": "unknown"
        }

analyzer = DummyAnalyzer()

# a simple "last summary" holder (updated by trading loop if any)
_last_summary = {"long_count": 0, "short_count": 0, "spike_count": 0, "trend": "neutral", "volatility": "unknown"}

# load NEWSAPI key from environment (optional)
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", None)

# ---------------------
# JSON data endpoint: returns the data used by charts and panels
# ---------------------
@app.route("/status/data")
def status_data():
    """
    Returns JSON used by frontend to update charts and panels.
    Should be fast and lightweight.
    """
    try:
        # BTC price history (default past 1d 1h)
        price_history = data_agg.get_price_history(symbol="BTC-USD", period="1d", interval="1h")

        # win rate and history from state
        win_rate = state.get_win_rate()
        win_rate_history = state.get_win_rate_history()

        # balance and positions realtime
        balance = executor.get_account_balance_usd()
        positions = state.get_all_active_positions()

        # last summary (from analyzer or stored)
        summary = _last_summary

        # external: fng, trending coins summary
        fng = data_agg.get_fear_and_greed_index()
        trending = data_agg.get_trending_coins()

        # latest news: english + japanese (up to 5 each) -- consumes translator if available
        news = data_agg.get_latest_news(newsapi_key=NEWSAPI_KEY, english_limit=5, japanese_limit=5)

        payload = {
            "price_history": price_history,
            "win_rate": win_rate,
            "win_rate_history": win_rate_history,
            "balance": balance,
            "positions": positions,
            "summary": summary,
            "external": {
                "fear_and_greed_index": fng,
                "trending_coins": trending,
                "news": news
            },
            "timestamp": int(time.time())
        }
        return jsonify(payload)
    except Exception as e:
        logger.exception("Failed to build status data")
        return jsonify({"error": str(e)}), 500

# ---------------------
# Rendered HTML dashboard (consumes /status/data via fetch and updates charts/text)
# ---------------------
STATUS_HTML = """
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>Bot Status Dashboard</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial; background:#f4f6f8; color:#222; margin: 0; padding: 24px; }
    .container{max-width:1100px;margin:0 auto}
    header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
    .card{background:#fff;border-radius:10px;padding:18px;margin-bottom:16px;box-shadow:0 3px 12px rgba(0,0,0,0.06)}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
    .small{font-size:0.9rem;color:#666}
    .title{font-size:1.15rem;margin-bottom:8px}
    .positions-list li{margin-bottom:8px}
    .news-list li{margin-bottom:12px}
    .tag{display:inline-block;padding:4px 8px;border-radius:6px;font-size:12px;color:#fff;margin-right:8px}
    .tag-en{background:#007bff}
    .tag-ja{background:#28a745}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🤖 Trading Bot — Status Dashboard</h1>
      <div class="small">Last update: <span id="lastUpdated">-</span></div>
    </header>

    <div class="grid">
      <div class="card">
        <div class="title">📊 Performance</div>
        <div>Win Rate: <strong id="winRate">-</strong> %</div>
        <div>Balance (USD): <strong id="balance">-</strong></div>
      </div>

      <div class="card">
        <div class="title">📈 Summary</div>
        <div>Long signals: <span id="longCount">-</span></div>
        <div>Short signals: <span id="shortCount">-</span></div>
        <div>Spike detections: <span id="spikeCount">-</span></div>
      </div>

      <div class="card">
        <div class="title">💰 Positions</div>
        <ul class="positions-list" id="positionsList"><li>No active positions</li></ul>
      </div>
    </div>

    <div class="card">
      <div class="title">📉 BTC (1h) — Last 24h</div>
      <canvas id="priceChart" height="120"></canvas>
    </div>

    <div class="card">
      <div class="title">📈 Win Rate History</div>
      <canvas id="winChart" height="120"></canvas>
    </div>

    <div class="card">
      <div class="title">🌍 Market Context</div>
      <div>Fear & Greed: <strong id="fng">-</strong></div>
      <div class="small">Trend / Volatility: <span id="trendVol">-</span></div>
      <div style="margin-top:8px"><strong>Trending Coins:</strong>
        <ul id="trendingList"></ul>
      </div>
    </div>

    <div class="card">
      <div class="title">📰 Latest News (EN & JP)</div>
      <ul class="news-list" id="newsList"></ul>
    </div>
  </div>

<script>
let priceChart, winChart;

function buildCharts() {
  const priceCtx = document.getElementById("priceChart").getContext("2d");
  priceChart = new Chart(priceCtx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'BTC / USD',
        data: [],
        borderColor: 'rgba(33,150,243,1)',
        tension: 0.2,
        fill: false,
        pointRadius: 2
      }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });

  const winCtx = document.getElementById("winChart").getContext("2d");
  winChart = new Chart(winCtx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Win Rate (%)',
        data: [],
        borderColor: 'rgba(40,167,69,1)',
        tension: 0.2,
        fill: false,
        pointRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { min: 0, max: 100 } }
    }
  });
}

function renderPositions(positions) {
  const ul = document.getElementById("positionsList");
  ul.innerHTML = "";
  const keys = Object.keys(positions || {});
  if (keys.length === 0) {
    ul.innerHTML = "<li>No active positions</li>";
    return;
  }
  keys.forEach(k => {
    const p = positions[k];
    const li = document.createElement("li");
    li.innerHTML = `<strong>${k}</strong> — ${p.side.toUpperCase()} @ ${p.entry_price} (size: ${p.position_size})<br>
                    TP: ${p.take_profit} / SL: ${p.stop_loss}`;
    ul.appendChild(li);
  });
}

function renderTrending(list) {
  const ul = document.getElementById("trendingList");
  ul.innerHTML = "";
  if (!list || list.length === 0) { ul.innerHTML = "<li>—</li>"; return; }
  list.forEach(c => {
    const li = document.createElement("li");
    li.textContent = `${c.name || c.id} (${(c.symbol||'').toUpperCase()}) — rank #${c.market_cap_rank || '-'}`
    ul.appendChild(li);
  });
}

function renderNews(news) {
  const ul = document.getElementById("newsList");
  ul.innerHTML = "";
  if (!news || news.length === 0) { ul.innerHTML = "<li>No news</li>"; return; }
  news.forEach(n => {
    const li = document.createElement("li");
    const langTag = document.createElement("span");
    langTag.className = "tag " + (n.lang === 'en' ? 'tag-en' : 'tag-ja');
    langTag.textContent = n.lang.toUpperCase();
    li.appendChild(langTag);
    const title = document.createElement("span");
    if (n.lang === 'en') {
      // show translated (if available) then original
      const tja = n.title_ja ? n.title_ja : n.title_en;
      title.innerHTML = `<strong>${tja}</strong><br><small>(${n.title_en || ''})</small>`;
    } else {
      title.innerHTML = `<strong>${n.title}</strong>`;
    }
    li.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "small";
    meta.innerHTML = ` — ${n.source || ''} <a href="${n.url}" target="_blank">link</a>`;
    li.appendChild(meta);
    ul.appendChild(li);
  });
}

async function fetchDataAndUpdate() {
  try {
    const res = await fetch("/status/data");
    if (!res.ok) throw new Error("Fetch failed");
    const d = await res.json();

    document.getElementById("lastUpdated").textContent = new Date(d.timestamp * 1000).toLocaleString();
    document.getElementById("winRate").textContent = d.win_rate;
    document.getElementById("balance").textContent = d.balance.toFixed ? d.balance.toFixed(2) : d.balance;

    // summary
    document.getElementById("longCount").textContent = d.summary.long_count ?? 0;
    document.getElementById("shortCount").textContent = d.summary.short_count ?? 0;
    document.getElementById("spikeCount").textContent = d.summary.spike_count ?? 0;

    // positions
    renderPositions(d.positions);

    // price chart update
    const ph = d.price_history || {timestamps:[], prices:[]};
    priceChart.data.labels = ph.timestamps;
    priceChart.data.datasets[0].data = ph.prices;
    priceChart.update();

    // win rate history update
    const wr = d.win_rate_history || {timestamps:[], values:[]};
    winChart.data.labels = wr.timestamps;
    winChart.data.datasets[0].data = wr.values;
    winChart.update();

    // market context
    const f = d.external.fear_and_greed_index || {};
    document.getElementById("fng").textContent = (f.value ? `${f.value} (${f.classification || ''})` : "N/A");
    document.getElementById("trendVol").textContent = `${d.summary.trend || '-'} / ${d.summary.volatility || '-'}`;
    renderTrending(d.external.trending_coins || []);
    renderNews(d.external.news || []);

  } catch (err) {
    console.error("Update failed", err);
  }
}

window.addEventListener('load', () => {
  buildCharts();
  fetchDataAndUpdate();
  // update only data every 60s
  setInterval(fetchDataAndUpdate, 60 * 1000);
});
</script>
</body>
</html>
"""

@app.route("/status")
def status_page():
    # return the dashboard HTML that will call /status/data
    return render_template_string(STATUS_HTML)

# ---------------------
# Example: background scheduler stub (optional). If you have a trading loop, call it here
# ---------------------
def background_loop():
    # placeholder loop that could run your trading cycle; we don't start heavy work here by default
    while True:
        # if your trading loop updates _last_summary or state, it will be reflected in /status/data
        time.sleep(60)

# start background thread (daemon) to keep compatibility if required
thread = Thread(target=background_loop, daemon=True)
thread.start()

# ---------------------
# Entrypoint
# ---------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting Flask on port %d", port)
    app.run(host="0.0.0.0", port=port)
