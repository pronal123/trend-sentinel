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
# from utils import api_retry_decorator (utils.pyを作成した場合)

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
# ... (他のWebページルート)

# --- 4. メインロジック ---
def run_trading_cycle():
    if not IS_BOT_ACTIVE: logging.warning("BOT is INACTIVE."); return
    logging.info("--- 🚀 Starting Trading Cycle ---")

    # --- フェーズ1: 保留中シグナルの確認と実行 ---
    pending_signals = state.get_and_clear_pending_signals()
    if pending_signals:
        logging.info(f"Confirming {len(pending_signals)} pending signal(s)...")
        for token_id, details in pending_signals.items():
            current_price = data_agg.get_latest_price(token_id)
            if current_price and current_price >= details['entry_price']:
                logging.info(f"✅ Signal for {token_id} CONFIRMED.")
                score = details['score']
                trade_amount = 50 + (score - 70) * 2.5 # スコアに応じて取引額を動的に決定
                trader.open_long_position(
                    token_id, details['series'], trade_amount_usd=trade_amount,
                    reason=details['reason'], notifier=notifier, win_rate=state.get_win_rate()
                )
            else:
                logging.info(f"❌ Signal for {token_id} REJECTED (price moved unfavorably).")

    # --- フェーズ2: 既存ポジションの監視 ---
    trader.check_active_positions(data_agg)
    
    # --- フェーズ3: 新規シグナルの生成 ---
    btc_series = data_agg.get_historical_data('BTC-USD', '1y')
    market_regime = 'RANGING' if btc_series is None or btc_series.empty else regime_detector.get_market_regime(btc_series)
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    entry_threshold = 65 if market_regime == 'TRENDING' else 75 # 動的閾値
    
    candidate_tokens = data_agg.get_top_tokens()
    if candidate_tokens is None: return

    for token in candidate_tokens:
        if state.has_position(token['id']): continue
        yf_ticker = f"{token['symbol'].upper()}-USD"
        score, series, _ = scorer.calculate_total_score(token, yf_ticker, fng_data, market_regime)
        if score >= entry_threshold:
            signal_details = {
                'score': score, 'series': series, 'entry_price': series['close'].iloc[-1],
                'reason': f"総合スコア {score:.1f}% (閾値: {entry_threshold}%)"
            }
            state.add_pending_signal(token['id'], signal_details)
            break
            
    logging.info("--- ✅ Trading Cycle Finished ---")

# --- 5. スケジューラ ---
def run_scheduler():
    logging.info("Scheduler started.")
    schedule.every(15).minutes.do(run_trading_cycle)
    # ... (他の hourly, daily ジョブ)
    while True:
        schedule.run_pending(); time.sleep(1)

# --- 6. プログラム起動 ---
if __name__ == "__main__":
    logging.info("Initializing Bot...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
