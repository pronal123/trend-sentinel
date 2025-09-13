# main.py
import schedule
import time
import logging
import threading
from flask import Flask
from datetime import datetime
import pytz

# モジュールをインポート
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
from telegram_notifier import TelegramNotifier
from state_manager import StateManager
from trading_executor import TradingExecutor # 追加
import risk_filter

# --- 初期設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
analyzer = AnalysisEngine()
trader = TradingExecutor(state) # stateを共有
notifier = TelegramNotifier()
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Auto Trading Bot is alive!"

def run_trading_cycle():
    jst = pytz.timezone('Asia/Tokyo')
    logging.info(f"--- Starting Trading Cycle at {datetime.now(jst).strftime('%H:%M:%S JST')} ---")
    
    # 1. データ収集 -> リスク除外
    all_data = data_agg.get_all_chains_data()
    if all_data.empty: return
    safe_data = risk_filter.filter_risky_tokens(all_data)

    # 2. 分析
    long_df, short_df, spike_df, summary = analyzer.run_analysis(safe_data)

    # 3. 通知 (重複防止)
    long_to_notify = long_df[long_df['symbol'].apply(state.can_notify)]
    # ... (同様にshort, spikeも)
    notifier.send_notification(long_to_notify, short_df, spike_df, summary)
    state.record_notification(long_to_notify)
    # ...

    # 4. 取引実行
    logging.info("--- Executing Trades based on analysis ---")
    # LONG候補のトップ1銘柄を取引 (一度に多くのポジションを持たない戦略)
    if not long_to_notify.empty:
        top_long_candidate = long_to_notify.iloc[0]
        logging.info(f"Top LONG candidate: {top_long_candidate['symbol'].upper()}")
        trader.execute_long(top_long_candidate['id'])
    
    # SHORT候補に合致する保有中の銘柄があれば売却
    for _, short_candidate in short_df.iterrows():
        if state.has_position(short_candidate['id']):
            logging.info(f"SHORT signal for owned asset: {short_candidate['symbol'].upper()}")
            trader.execute_short(short_candidate['id'])

    logging.info("--- Trading Cycle Finished ---")

# ... (run_daily_summary, run_scheduler, __main__部分は前回と同様)
def run_scheduler():
    schedule.every().day.at("02:00", "Asia/Tokyo").do(run_trading_cycle)
    # ... 他のスケジュール
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
