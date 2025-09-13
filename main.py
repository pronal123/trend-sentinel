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
from market_regime_detector import MarketRegimeDetector # <--- 新規インポート

# --- 3. ログと各クラスのインスタンス化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
sentiment_analyzer = SentimentAnalyzer()
notifier = TelegramNotifier()
regime_detector = MarketRegimeDetector() # <--- 新規インスタンス化

# --- 4. Webサーバー ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return f"✅ Auto Trading Bot is {'ACTIVE' if IS_BOT_ACTIVE else 'INACTIVE'}!"

# --- 5. メインの取引・通知ロジック ---
def run_trading_cycle():
    if not IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping trading cycle."); return

    logging.info("--- 🚀 Starting Trading Cycle ---")
    
    # 1. 市場レジームを判断 (例としてBTCのデータを使用)
    btc_series = data_agg.get_historical_data('BTC-USD', '1y')
    if btc_series.empty:
        logging.warning("Could not fetch BTC data for regime detection. Defaulting to RANGING.")
        market_regime = 'RANGING'
    else:
        market_regime = regime_detector.get_market_regime(btc_series)

    # 2. センチメント取得とポジション監視
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    trader.check_active_positions(data_agg)

    # 3. 新規参入の判断
    candidate_tokens = data_agg.get_top_tokens()
    
    for token in candidate_tokens:
        if state.has_position(token['id']): continue

        yf_ticker = f"{token['symbol'].upper()}-USD"
        
        # スコア計算時に市場レジームを渡す
        score, series = scorer.calculate_total_score(
            token, yf_ticker, fng_data, market_regime
        )

        if score >= 70:
            reason = f"総合スコア {score:.1f}% (レジーム: {market_regime})"
            trader.open_long_position(
                token['id'], series, reason=reason, 
                notifier=notifier, win_rate=state.get_win_rate()
            )
            break
    
    logging.info("--- ✅ Trading Cycle Finished ---")

# ... (run_hourly_status_update, run_scheduler, __main__部分は前回と同様)
def run_scheduler():
    logging.info("Scheduler started. Waiting for tasks...")
    schedule.every(15).minutes.do(run_trading_cycle)
    # ... (他のスケジュール)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.info("Initializing Bot...")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
