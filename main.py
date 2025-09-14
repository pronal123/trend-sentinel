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
    <title>Bot Status Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f4f6f9; color: #333; padding: 2rem; }
        .container { max-width: 960px; margin: auto; }
        h1, h2 { text-align: center; color: #1a1a1a; }
        h2 { margin-top: 2.5rem; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
        .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem; text-align: center; margin: 2rem 0; }
        .grid-item { background: white; padding: 1.5rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .grid-item .label { font-size: 1.1rem; color: #555; }
        .grid-item .value { font-size: 2rem; font-weight: bold; color: #1a1a1a; margin-top: 0.5rem; }
        .analysis-box { margin-top: 2rem; padding: 1.5rem; background: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .analysis-box h2 { text-align: left; margin-top: 0; }
        .analysis-box pre { white-space: pre-wrap; word-wrap: break-word; font-family: 'SF Mono', 'Menlo', 'Monaco', monospace; font-size: .9rem; line-height: 1.7; color: #444; background: #f9f9f9; padding: 1rem; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px; overflow: hidden; }
        th, td { padding: 1rem; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f7f7f9; }
        .profit { color: #28a745; }
        .loss { color: #dc3545; }
        .no-positions { text-align: center; padding: 2rem; color: #888; background: white; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Bot Status Dashboard</h1>
        <div class="grid-container">
            <div class="grid-item">
                <div class="label">現在の総資産残高</div>
                <div class="value">${{ "%.2f"|format(total_balance) }}</div>
            </div>
            <div class="grid-item">
                <div class="label">市場センチメント</div>
                <div class="value">{{ sentiment.sentiment }} ({{ sentiment.value }})</div>
            </div>
            <div class="grid-item">
                <div class="label">市場レジーム</div>
                <div class="value">{{ market_regime }}</div>
            </div>
        </div>
        
        <div class="analysis-box">
            <h2>AIによる市場分析コメント (BTC-USD)</h2>
            <pre>{{ analysis_comments }}</pre>
        </div>
        
        <h2>アクティブなポジション</h2>
        {% if positions %}
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Entry / Current</th>
                        <th>Unrealized P/L</th>
                        <th>Take Profit</th>
                        <th>Stop Loss</th>
                    </tr>
                </thead>
                <tbody>
                    {% for pos in positions %}
                        <tr class="{{ 'profit' if pos.pnl_percent >= 0 else 'loss' }}">
                            <td><strong>{{ pos.ticker }}</strong></td>
                            <td>${{ "%.4f"|format(pos.entry_price) }}<br>→ ${{ "%.4f"|format(pos.current_price) }}</td>
                            <td><strong>{{ "%.2f"|format(pos.pnl_percent) }}%</strong> (${{ "%.2f"|format(pos.pnl) }})</td>
                            <td class="profit">${{ "%.4f"|format(pos.take_profit) }}</td>
                            <td class="loss">${{ "%.4f"|format(pos.stop_loss) }}</td>
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
<!DOCTYPE html><html lang="ja"><head><title>Bot Admin Panel</title><style>body{font-family:sans-serif;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.container{background:white;padding:2rem;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.1);text-align:center}h1{color:#333}input{padding:.5rem;width:80%;margin-bottom:1rem;border:1px solid #ccc;border-radius:4px}button{padding:.7rem 1.5rem;border:none;background-color:#007bff;color:white;border-radius:4px;cursor:pointer;font-size:1rem}button:hover{background-color:#0056b3}#response{margin-top:1rem;font-weight:700}</style></head>
<body><div class="container"><h1>🤖 Bot Admin Panel</h1><div><input type="password" id="secretKey" placeholder="Enter Train Secret Key"></div><div><button onclick="triggerRetrain()">Retrain AI Model</button></div><p id="response"></p></div>
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
    total_balance = trader.get_account_balance_usd() or 0.0
    
    btc_series = data_agg.get_historical_data('BTC-USD', '1y')
    market_regime = 'データ取得失敗'
    analysis_comments = "市場データの取得に失敗したため、分析できません。"
    sentiment_data = sentiment_analyzer.get_fear_and_greed_index() or {'value': 'N/A', 'sentiment': 'Unknown'}
    
    if btc_series is not None and not btc_series.empty:
        market_regime = regime_detector.get_market_regime(btc_series)
        _, _, analysis_comments = scorer.calculate_total_score(
            {'symbol': 'BTC', 'id': 'bitcoin'}, btc_series, sentiment_data, market_regime
        )
    
    active_positions = state.get_all_positions()
    enriched_positions = []
    if active_positions:
        for token_id, details in active_positions.items():
            price = data_agg.get_latest_price(token_id)
            if price:
                details['current_price'] = price
                size = details.get('position_size', 1)
                details['pnl'] = (price - details['entry_price']) * size
                details['pnl_percent'] = (price / details['entry_price'] - 1) * 100
                enriched_positions.append(details)
                
    return render_template_string(
        STATUS_PAGE_HTML, 
        positions=enriched_positions, 
        total_balance=total_balance,
        market_regime=market_regime,
        sentiment=sentiment_data,
        analysis_comments=analysis_comments
    )

@app.route('/retrain', methods=['POST'])
def retrain_model():
    auth_key = request.json.get('secret_key')
    if auth_key != TRAIN_SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    logging.info("Remote retraining process triggered.")
    # TODO: 実際の再学習ロジックを非同期で呼び出す
    return jsonify({"message": "Model retraining process started."}), 202

# --- 5. メインの取引・通知ロジック ---
def run_trading_cycle():
    if not IS_BOT_ACTIVE: logging.warning("BOT is INACTIVE."); return
    logging.info("--- 🚀 Starting Trading Cycle ---")

    # フェーズ1: 保留中シグナルの確認と実行
    pending_signals = state.get_and_clear_pending_signals()
    if pending_signals:
        for token_id, details in pending_signals.items():
            current_price = data_agg.get_latest_price(token_id)
            if current_price and current_price >= details['entry_price']:
                logging.info(f"✅ Signal for {token_id} CONFIRMED.")
                score = details['score']
                trade_amount = 50 + (score - 70) * 2.5
                trader.open_long_position(
                    token_id, details['series'], trade_amount_usd=trade_amount,
                    reason=details['reason'], notifier=notifier, win_rate=state.get_win_rate()
                )
            else:
                logging.info(f"❌ Signal for {token_id} REJECTED.")

    # フェーズ2: 既存ポジションの監視
    trader.check_active_positions(data_agg, notifier=notifier)
    
    # フェーズ3: 新規シグナルの生成
    btc_series = data_agg.get_historical_data('BTC-USD', '1y')
    if btc_series is None or btc_series.empty:
        logging.warning("Could not fetch BTC data for analysis. Skipping this trading cycle.")
        return

    market_regime = regime_detector.get_market_regime(btc_series)
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    entry_threshold = 65 if market_regime == 'TRENDING' else 75
    
    candidate_tokens = data_agg.get_top_tokens()
    if not candidate_tokens: return

    for token in candidate_tokens:
        if state.has_position(token['id']): continue
        yf_ticker = f"{token['symbol'].upper()}-USD"
        series = data_agg.get_historical_data(yf_ticker, '1y')
        score, _ = scorer.calculate_total_score(token, series, fng_data, market_regime)
        logging.info(f"Analysis complete for {yf_ticker}. Score: {score:.2f}")
        if score >= entry_threshold:
            signal_details = {
                'score': score, 'series': series, 'entry_price': series['close'].iloc[-1],
                'reason': f"総合スコア {score:.1f}% (閾値: {entry_threshold}%)"
            }
            state.add_pending_signal(token['id'], signal_details)
            break
            
    logging.info("--- ✅ Trading Cycle Finished ---")

def run_hourly_status_update():
    logging.info("--- 🕒 Hourly Status Update ---")
    active_positions = state.get_all_positions()
    if not active_positions: 
        logging.info("No active positions.")
        notifier.send_position_status_update([])
        return
    enriched_positions = []
    for token_id, details in active_positions.items():
        price = data_agg.get_latest_price(token_id)
        if price: enriched_positions.append({**details, 'current_price': price})
    notifier.send_position_status_update(enriched_positions)
    
def run_daily_balance_update():
    """1日1回、残高をTelegramに通知する"""
    logging.info("--- ☀️ Daily Balance Update ---")
    total_balance = trader.get_account_balance_usd()
    notifier.send_balance_update(total_balance)

# --- 6. スケジューラの定義と実行 ---
def run_scheduler():
    logging.info("Scheduler started.")
    jst = pytz.timezone('Asia/Tokyo')
    schedule.every(15).minutes.do(run_trading_cycle)
    schedule.every(1).hour.do(run_hourly_status_update)
    schedule.every().day.at("09:00", jst).do(run_daily_balance_update)
    while True:
        schedule.run_pending(); time.sleep(1)

# --- 7. プログラムの起動 ---
if __name__ == "__main__":
    logging.info("Initializing Bot...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
