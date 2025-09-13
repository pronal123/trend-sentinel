# main.py
import os, threading, time, logging, schedule, pytz
from flask import Flask
from dotenv import load_dotenv

load_dotenv()
IS_BOT_ACTIVE = os.environ.get("BOT_ACTIVE", "false").lower() in ("true", "1", "yes")

from state_manager import StateManager
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
from telegram_notifier import TelegramNotifier
from trading_executor import TradingExecutor
import risk_filter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
analyzer = AnalysisEngine()
trader = TradingExecutor(state)
notifier = TelegramNotifier()
app = Flask(__name__)

@app.route('/')
def health_check():
    return f"Auto Trading Bot is {'ACTIVE' if IS_BOT_ACTIVE else 'INACTIVE'}!"

def run_trading_cycle():
    if not IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping trading cycle.")
        return
    
    logging.info("--- Starting Trading Cycle ---")
    all_data = data_agg.get_all_chains_data()
    if all_data.empty: return
    safe_data = risk_filter.filter_risky_tokens(all_data)
    long_df, short_df, spike_df, summary = analyzer.run_analysis(safe_data)

    long_to_notify = long_df[long_df['symbol'].apply(state.can_notify)]
    notifier.send_notification(long_to_notify, short_df, spike_df, summary)
    state.record_notification(long_to_notify)

    if not long_to_notify.empty:
        top_long = long_to_notify.iloc[0]
        trader.execute_long(top_long['id'])
    
    for _, short_row in short_df.iterrows():
        if state.has_position(short_row['id']):
            trader.execute_short(short_row['id'])
            
    logging.info("--- Trading Cycle Finished ---")

def run_scheduler():
    logging.info("Scheduler started.")
    jst = pytz.timezone('Asia/Tokyo')
    schedule.every().day.at("02:00", jst).do(run_trading_cycle)
    schedule.every().day.at("08:00", jst).do(run_trading_cycle)
    schedule.every().day.at("14:00", jst).do(run_trading_cycle)
    schedule.every().day.at("20:00", jst).do(run_trading_cycle)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
