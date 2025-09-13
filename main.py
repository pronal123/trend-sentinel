# main.py
import logging, schedule, time, threading
from dotenv import load_dotenv

# --- 初期化 ---
load_dotenv()
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
# ... (その他、Flaskなど)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
# ...

def run_trading_cycle():
    logging.info("--- Starting Trading Cycle ---")
    
    # 1. 既存ポジションの監視・決済
    trader.check_active_positions(data_agg)

    # 2. 新規参入の判断
    # 監視対象リストを取得 (例: CoinGeckoの上位銘柄)
    candidate_tokens = data_agg.get_top_tokens() 
    
    for token in candidate_tokens:
        # 既にポジションを持っている銘柄はスキップ
        if state.has_position(token['id']):
            continue

        # スコアを計算
        yf_ticker = f"{token['symbol'].upper()}-USD" # yfinance用のティッカー
        score, series = scorer.calculate_total_score(token['id'], yf_ticker)

        # 総合得点が70%を超えたら新規ロングポジションを持つ
        if score >= 70:
            logging.info(f"🔥 ENTRY SIGNAL: Score for {token['symbol']} is {score:.1f} (>= 70). Opening long position.")
            trader.open_long_position(token['id'], series)
            # 1回のサイクルで1ポジションのみ（ドカ買い防止）
            break 
    
    logging.info("--- Trading Cycle Finished ---")

# --- スケジューラとWebサーバー起動 ---
# ... (前回と同様、run_schedulerとif __name__ == "__main__")
# 実行間隔は短くする（例：5分ごと）
def run_scheduler():
    logging.info("Scheduler started.")
    schedule.every(5).minutes.do(run_trading_cycle)
    # ...
