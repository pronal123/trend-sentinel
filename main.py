# main.py
import os
import threading
import time
import logging
import schedule
import pytz
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --------------------------------------------------------------------
# 1. 初期設定 & 環境変数読み込み
# --------------------------------------------------------------------
# .envファイルをロードして、環境変数をPythonから読めるようにする
load_dotenv()

# BOTの稼働スイッチを環境変数から読み込む (デフォルトは'false')
IS_BOT_ACTIVE = os.environ.get("BOT_ACTIVE", "false").lower() in ("true", "1", "yes")
DATABASE_URL = os.environ.get("DATABASE_URL")
TRAIN_SECRET_KEY = os.environ.get("TRAIN_SECRET_KEY")

# --------------------------------------------------------------------
# 2. 必要なモジュールとクラスをインポート
# --------------------------------------------------------------------
# (各ファイルが同じディレクトリにあることを前提とします)
import ml_model
from state_manager import StateManager
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from sentiment_analyzer import SentimentAnalyzer
from telegram_notifier import TelegramNotifier

# --------------------------------------------------------------------
# 3. ログ設定と各クラスのインスタンス化
# --------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
sentiment_analyzer = SentimentAnalyzer()
notifier = TelegramNotifier()

# --------------------------------------------------------------------
# 4. Webサーバー (Renderのヘルスチェック & 管理ページ)
# --------------------------------------------------------------------
# Gunicornがこの'app'という名前の変数を見つけて起動する
app = Flask(__name__)

ADMIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Admin Panel</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; width: 90%; max-width: 400px; }
        h1 { color: #333; margin-bottom: 1.5rem; }
        input { font-size: 1rem; padding: 0.7rem; width: calc(100% - 1.4rem); margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 0.8rem 1.5rem; border: none; background-color: #007bff; color: white; border-radius: 4px; cursor: pointer; font-size: 1rem; transition: background-color 0.2s; }
        button:hover { background-color: #0056b3; }
        #response { margin-top: 1.5rem; font-weight: bold; min-height: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Bot Admin Panel</h1>
        <div>
            <input type="password" id="secretKey" placeholder="Enter Train Secret Key">
        </div>
        <div>
            <button onclick="triggerRetrain()">Retrain AI Model</button>
        </div>
        <p id="response"></p>
    </div>
    <script>
        async function triggerRetrain() {
            const secretKey = document.getElementById('secretKey').value;
            const responseElement = document.getElementById('response');
            if (!secretKey) {
                responseElement.style.color = 'red';
                responseElement.textContent = 'Error: Secret Key is required.';
                return;
            }
            responseElement.textContent = 'Sending request...';
            try {
                const response = await fetch('/retrain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ secret_key: secretKey })
                });
                const data = await response.json();
                if (response.ok) {
                    responseElement.style.color = 'green';
                    responseElement.textContent = `Success: ${data.message}`;
                } else {
                    responseElement.style.color = 'red';
                    responseElement.textContent = `Error: ${data.error || 'Unknown error'}`;
                }
            } catch (error) {
                responseElement.style.color = 'red';
                responseElement.textContent = `Network Error: ${error}`;
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def health_check():
    """RenderがBOTの生存確認をするためのWebページ"""
    if IS_BOT_ACTIVE:
        return "✅ Auto Trading Bot is ACTIVE and running!"
    else:
        return "🚫 Auto Trading Bot is INACTIVE (standby mode)."

@app.route('/admin')
def admin_panel():
    """ブラウザでAIモデルの再学習をトリガーするための管理ページ"""
    return ADMIN_PAGE_HTML

@app.route('/retrain', methods=['POST'])
def retrain_model():
    """AIモデルの再学習をトリガーするAPI（管理ページから呼び出される）"""
    auth_key = request.json.get('secret_key')
    if auth_key != TRAIN_SECRET_KEY:
        return jsonify({"error": "Unauthorized - Invalid Secret Key"}), 401
    
    # TODO: 実際の再学習ロジックを呼び出す
    logging.info("Remote retraining process triggered via admin panel.")
    # training_thread = threading.Thread(target=ml_model.run_daily_retraining, args=(db_engine, data_agg))
    # training_thread.start()
    
    return jsonify({"message": "Model retraining process started in the background."}), 202

# --------------------------------------------------------------------
# 5. メインの取引ロジック
# --------------------------------------------------------------------
def run_trading_cycle():
    if not IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping trading cycle.")
        return

    logging.info("--- 🚀 Starting Trading Cycle ---")
    
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    trader.check_active_positions(data_agg)
    candidate_tokens = data_agg.get_top_tokens()
    
    for token in candidate_tokens:
        if state.has_position(token['id']): continue

        yf_ticker = f"{token['symbol'].upper()}-USD"
        score, series = scorer.calculate_total_score(token['id'], yf_ticker, fng_data)

        if score >= 70:
            logging.info(f"🔥 ENTRY SIGNAL: Score for {token['symbol']} is {score:.1f} (>= 70). Opening long position.")
            trader.open_long_position(token['id'], series)
            break
    
    logging.info("--- ✅ Trading Cycle Finished ---")

# --------------------------------------------------------------------
# 6. スケジューラの定義と実行
# --------------------------------------------------------------------
def run_scheduler():
    logging.info("Scheduler started. Waiting for tasks...")
    # ポジション管理のため、実行間隔は15分ごとを推奨
    schedule.every(15).minutes.do(run_trading_cycle)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# --------------------------------------------------------------------
# 7. プログラムの起動
# --------------------------------------------------------------------
if __name__ == "__main__":
    logging.info("Initializing Bot...")

    # スケジューラをバックグラウンドのスレッドで実行
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # RenderでWeb Serviceとして稼働させるためにFlaskサーバーを起動
    port = int(os.environ.get("PORT", 8080))
    # Gunicornが本番環境で起動するため、app.runはローカルテスト用
    app.run(host='0.0.0.0', port=port)
