# main.py
import os
import threading
import time
import logging
import schedule
import pytz
from flask import Flask, jsonify, render_template_string
from dotenv import load_dotenv

# --- 1. 初期設定 & 環境変数読み込み ---
load_dotenv()
IS_BOT_ACTIVE = os.environ.get("BOT_ACTIVE", "false").lower() in ("true", "1", "yes")
TRAIN_SECRET_KEY = os.environ.get("TRAIN_SECRET_KEY")

# --- 2. 必要なモジュールとクラスをインポート ---
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from sentiment_analyzer import SentimentAnalyzer
from telegram_notifier import TelegramNotifier
from market_regime_detector import MarketRegimeDetector

# --- 3. ログと各クラスのインスタンス化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
sentiment_analyzer = SentimentAnalyzer()
notifier = TelegramNotifier()
regime_detector = MarketRegimeDetector()

# --- 4. Webサーバー (Renderのヘルスチェック & 管理/ステータスページ) ---
app = Flask(__name__)

STATUS_PAGE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Position Status</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; padding: 2rem; }
        .container { max-width: 800px; margin: auto; background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #1a1a1a; }
        table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; }
        th, td { padding: 0.8rem; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f7f7f7; }
        .profit { color: #28a745; }
        .loss { color: #dc3545; }
        .no-positions { text-align: center; padding: 2rem; color: #888; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Bot Position Status</h1>
        {% if positions %}
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Entry Price</th>
                        <th>Current Price</th>
                        <th>Unrealized P/L</th>
                    </tr>
                </thead>
                <tbody>
                    {% for pos in positions %}
                        <tr class="{{ 'profit' if pos.pnl_percent >= 0 else 'loss' }}">
                            <td><strong>{{ pos.ticker }}</strong></td>
                            <td>${{ "%.4f"|format(pos.entry_price) }}</td>
                            <td>${{ "%.4f"|format(pos.current_price) }}</td>
                            <td><strong>{{ "%.2f"|format(pos.pnl_percent) }}%</strong> (${{ "%.2f"|format(pos.pnl) }})</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p class="no-positions">現在、アクティブなポジションはありません。</p>
        {% endif %}
    </div>
</body>
</html>
"""

ADMIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head><title>Bot Admin Panel</title><style>body{font-family:sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.container{background:white;padding:2rem;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.1);text-align:center}h1{color:#333}input{padding:.5rem;width:80%;margin-bottom:1rem;border:1px solid #ccc;border-radius:4px}button{padding:.7rem 1.5rem;border:none;background-color:#007bff;color:white;border-radius:4px;cursor:pointer;font-size:1rem}button:hover{background-color:#0056b3}#response{margin-top:1rem;font-weight:700}</style></head>
<body>
<div class="container"><h1>🤖 Bot Admin Panel</h1><div><input type="password" id="secretKey" placeholder="Enter Train Secret Key"></div><div><button onclick="triggerRetrain()">Retrain AI Model</button></div><p id="response"></p></div>
<script>async function triggerRetrain(){const e=document.getElementById("secretKey").value,t=document.getElementById("response");t.textContent="Sending request...";try{const n=await fetch("/retrain",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({secret_key:e})}),o=await n.json();n.ok?(t.style.color="green",t.textContent=`Success: ${o.message}`):(t.style.color="red",t.textContent=`Error: ${o.error||"Unknown error"}`)}catch(e){t.style.color="red",t.textContent=`Network Error: ${e}`}}</script>
</body></html>
"""

@app.route('/')
def health_check():
    return f"✅ Auto Trading Bot is {'ACTIVE' if IS_BOT_ACTIVE else 'INACTIVE'}!"

@app.route('/admin')
def admin_panel():
    return ADMIN_PAGE_HTML

@app.route('/status')
def position_status_page():
    active_positions_details = state.get_all_positions()
    enriched_positions = []
    if active_positions_details:
        for token_id, details in active_positions_details.items():
            current_price = data_agg.get_latest_price(token_id)
            if current_price:
                details['current_price'] = current_price
                position_size = details.get('position_size', (details.get('trade_amount_usd', 100) / details['entry_price']))
                details['pnl'] = (current_price - details['entry_price']) * position_size
                details['pnl_percent'] = (current_price / details['entry_price'] - 1) * 100
                enriched_positions.append(details)
    return render_template_string(STATUS_PAGE_HTML, positions=enriched_positions)

@app.route('/retrain', methods=['POST'])
def retrain_model():
    auth_key = request.json.get('secret_key')
    if auth_key != TRAIN_SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    logging.info("Remote retraining process triggered.")
    return jsonify({"message": "Model retraining process started."}), 202

# --- 5. メインの取引・通知ロジック ---
def run_trading_cycle():
    if not IS_BOT_ACTIVE: logging.warning("BOT is INACTIVE. Skipping cycle."); return
    logging.info("--- 🚀 Starting Trading Cycle ---")
    btc_series = data_agg.get_historical_data('BTC-USD', '1y')
    market_regime = 'RANGING' if btc_series.empty else regime_detector.get_market_regime(btc_series)
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    win_rate = state.get_win_rate()
    trader.check_active_positions(data_agg)
    for token in data_agg.get_top_tokens():
        if state.has_position(token['id']): continue
        yf_ticker = f"{token['symbol'].upper()}-USD"
        score, series = scorer.calculate_total_score(token, yf_ticker, fng_data, market_regime)
        logging.info(f"Analysis complete for {yf_ticker}. Score: {score:.2f}")
        if score >= 70:
            reason = f"総合スコア {score:.1f}% (レジーム: {market_regime})"
            trader.open_long_position(token['id'], series, reason=reason, notifier=notifier, win_rate=win_rate)
            break
    logging.info("--- ✅ Trading Cycle Finished ---")

def run_hourly_status_update():
    logging.info("--- 🕒 Hourly Status Update ---")
    active_positions = state.get_all_positions()
    if not active_positions: logging.info("No active positions."); notifier.send_position_status_update([]); return
    enriched_positions = []
    for token_id, details in active_positions.items():
        price = data_agg.get_latest_price(token_id)
        if price: enriched_positions.append({**details, 'current_price': price})
    notifier.send_position_status_update(enriched_positions)

# --- 6. スケジューラの定義と実行 ---
def run_scheduler():
    logging.info("Scheduler started.")
    schedule.every(15).minutes.do(run_trading_cycle)
    schedule.every(1).hour.do(run_hourly_status_update)
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- 7. プログラムの起動 ---
if __name__ == "__main__":
    logging.info("Initializing Bot...")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
