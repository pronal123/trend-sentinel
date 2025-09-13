# main.py
import logging, schedule, time, threading
from dotenv import load_dotenv

# --- 初期化 ---
load_dotenv()
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from sentiment_analyzer import SentimentAnalyzer # <--- インポート
# ... (その他、Flaskなど)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- クラスのインスタンス化 ---
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
sentiment_analyzer = SentimentAnalyzer() # <--- インスタンス化

# ... (Flaskアプリの定義など)

def run_trading_cycle():
    logging.info("--- Starting Trading Cycle ---")
    
    # 1. サイクル開始時に市場全体のセンチメントを一括で取得
    fng_data = sentiment_analyzer.get_fear_and_greed_index()

    # 2. 既存ポジションの監視・決済
    trader.check_active_positions(data_agg)

    # 3. 新規参入の判断
    candidate_tokens = data_agg.get_top_tokens()
    
    for token in candidate_tokens:
        if state.has_position(token['id']):
            continue

        # スコアを計算 (取得したセンチメントデータを渡す)
        yf_ticker = f"{token['symbol'].upper()}-USD"
        score, series = scorer.calculate_total_score(token['id'], yf_ticker, fng_data)

        if score >= 70:
            logging.info(f"🔥 ENTRY SIGNAL: Score for {token['symbol']} is {score:.1f} (>= 70). Opening long position.")
            trader.open_long_position(token['id'], series)
            break
    
    logging.info("--- Trading Cycle Finished ---")

# --- スケジューラとWebサーバー起動 ---
def run_scheduler():
    logging.info("Scheduler started.")
    # ポジション管理のため、実行間隔は短め（例: 15分ごと）を推奨
    schedule.every(15).minutes.do(run_trading_cycle)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ... (if __name__ == "__main__": 部分は変更なし)
