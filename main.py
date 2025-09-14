# main.py
import os, threading, time, logging, schedule, pytz
from flask import Flask
from dotenv import load_dotenv

# --- 1. 初期設定 & インポート ---
load_dotenv()
IS_BOT_ACTIVE = os.environ.get("BOT_ACTIVE", "false").lower() in ("true", "1", "yes")
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from sentiment_analyzer import SentimentAnalyzer
from telegram_notifier import TelegramNotifier
from market_regime_detector import MarketRegimeDetector

# --- 2. ログとクラスのインスタンス化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
sentiment_analyzer = SentimentAnalyzer()
notifier = TelegramNotifier()
regime_detector = MarketRegimeDetector()

# --- 3. Webサーバー ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return f"✅ Auto Trading Bot is {'ACTIVE' if IS_BOT_ACTIVE else 'INACTIVE'}!"

# --- 4. メインロジック ---
def run_trading_cycle():
    if not IS_BOT_ACTIVE: logging.warning("BOT is INACTIVE."); return
    logging.info("--- 🚀 Starting Trading Cycle ---")
    
    # 既存ポジションの監視
    trader.check_active_positions(data_agg, notifier=notifier)
    
    # 新規シグナルの生成
    btc_series = data_agg.get_historical_data('BTC-USD', '1y')
    if btc_series is None or btc_series.empty:
        logging.warning("Could not fetch BTC data for regime detection. Skipping signal generation.")
        return

    market_regime = regime_detector.get_market_regime(btc_series)
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    entry_threshold = 65 if market_regime == 'TRENDING' else 75
    
    candidate_tokens = data_agg.get_top_tokens()
    if not candidate_tokens: return

    for token in candidate_tokens:
        if state.has_position(token['id']): continue
        
        yf_ticker = f"{token['symbol'].upper()}-USD"
        score, series, _ = scorer.calculate_total_score(token, yf_ticker, fng_data, market_regime)
        
        if score >= entry_threshold:
            reason = f"総合スコア {score:.1f}% (閾値: {entry_threshold}%)"
            trade_amount = 50 + (score - 70) * 2.5 # 動的ポジションサイズ
            trader.open_long_position(
                token['id'], series, trade_amount_usd=trade_amount,
                reason=reason, notifier=notifier, win_rate=state.get_win_rate()
            )
            break
            
    logging.info("--- ✅ Trading Cycle Finished ---")

def run_hourly_status_update():
    # ... (前回と同様)
    pass
    
def run_daily_summary_job():
    logging.info("--- 📊 Daily Summary Job ---")
    notifier.send_daily_summary(state.get_win_rate(), state.trade_history)
    state.trade_history.clear() # 日次でリセット

# --- 5. スケジューラ ---
def run_scheduler():
    logging.info("Scheduler started.")
    jst = pytz.timezone('Asia/Tokyo')
    schedule.every(15).minutes.do(run_trading_cycle)
    schedule.every(1).hour.do(run_hourly_status_update)
    schedule.every().day.at("23:55", jst).do(run_daily_summary_job)
    
    while True:
        schedule.run_pending(); time.sleep(1)

# --- 6. プログラム起動 ---
if __name__ == "__main__":
    logging.info("Initializing Bot...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
