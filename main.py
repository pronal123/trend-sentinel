# main.py
import os
import threading
import time
import logging
import schedule
import pytz
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

# --- 5. メインの取引・通知ロジック ---
def run_trading_cycle():
    """15分ごとに実行されるメインの取引サイクル"""
    if not IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping trading cycle.")
        return

    logging.info("--- 🚀 Starting Trading Cycle ---")
    
    current_win_rate = state.get_win_rate()
    fng_data = sentiment_analyzer.get_fear_and_greed_index()
    trader.check_active_positions(data_agg)
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

def run_hourly_status_update():
    """1時間ごとに実行されるポジション状況の通知サイクル"""
    logging.info("--- 🕒 Hourly Status Update ---")
    
    active_positions_details = state.get_all_positions()
    if not active_positions_details:
        notifier.send_position_status_update([]) # ポジションがない場合も通知
        return

    # 各ポジションの最新価格を取得して情報を付加
    enriched_positions = []
    for token_id, details in active_positions_details.items():
        current_price = data_agg.get_latest_price(token_id)
        if current_price:
            enriched_positions.append({
                **details, # entry_price, tickerなど
                'current_price': current_price
            })
    
    notifier.send_position_status_update(enriched_positions)

# --- 6. スケジューラの定義と実行 ---
def run_scheduler():
    logging.info("Scheduler started. Waiting for tasks...")
    jst = pytz.timezone('Asia/Tokyo')
    
    # 取引サイクルのスケジュール (15分ごと)
    schedule.every(15).minutes.do(run_trading_cycle)

    # ポジション状況の通知スケジュール (毎時0分)
    schedule.every().hour.at(":00").do(run_hourly_status_update)
    
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
