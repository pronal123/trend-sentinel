# main.py
import os, threading, time, logging, schedule, pytz
from flask import Flask
from dotenv import load_dotenv

# --- 1. 初期設定 & 環境変数読み込み ---
load_dotenv()
IS_BOT_ACTIVE = os.environ.get("BOT_ACTIVE", "false").lower() in ("true", "1", "yes")

# --- 2. 必要なモジュールとクラスをインポート ---
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from sentiment_analyzer import SentimentAnalyzer
from telegram_notifier import TelegramNotifier

# --- 3. ログと各クラスのインスタンス化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
sentiment_analyzer = SentimentAnalyzer()
notifier = TelegramNotifier()

# --- 4. Webサーバー (Renderのヘルスチェック用) ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return f"✅ Auto Trading Bot is {'ACTIVE' if IS_BOT_ACTIVE else 'INACTIVE'}!"

# --- 5. メインの取引ロジック ---
def run_trading_cycle():
    if not IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping trading cycle.")
        return

    logging.info("--- 🚀 Starting Trading Cycle ---")
    
    # 1. サイクル開始時に現在の勝率を計算
    current_win_rate = state.get_win_rate()

    # 2. 市場全体のセンチメントを取得
    fng_data = sentiment_analyzer.get_fear_and_greed_index()

    # 3. 既存ポジションの監視・決済
    trader.check_active_positions(data_agg)

    # 4. 新規参入の判断
    candidate_tokens = data_agg.get_top_tokens()
    
    for token in candidate_tokens:
        if state.has_position(token['id']): continue

        yf_ticker = f"{token['symbol'].upper()}-USD"
        score, series = scorer.calculate_total_score(token['id'], yf_ticker, fng_data)

        if score >= 70:
            reason = f"総合スコア {score:.1f}% (>= 70%)"
            trader.open_long_position(
                token['id'], series, reason=reason, 
                notifier=notifier, win_rate=current_win_rate
            )
            break
    
    logging.info("--- ✅ Trading Cycle Finished ---")

# --- 6. スケジューラの定義と実行 ---
def run_scheduler():
    logging.info("Scheduler started. Waiting for tasks...")
    schedule.every(15).minutes.do(run_trading_cycle)
    
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
