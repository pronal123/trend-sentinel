# main.py
import os, threading, time, logging, schedule, pytz
from flask import Flask
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

# --- 環境変数とグローバル設定 ---
DATABASE_URL = os.environ.get("DATABASE_URL")
IS_BOT_ACTIVE = os.environ.get("BOT_ACTIVE", "false").lower() in ("true", "1", "yes")

# --- モジュールインポート & 初期化 ---
import ml_model # ml_modelを先にインポート
from state_manager import StateManager
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
# ... (他のインポート)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- データベース接続 ---
db_engine = None
if DATABASE_URL:
    try:
        db_engine = create_engine(DATABASE_URL)
        ml_model.Base.metadata.create_all(db_engine) # 起動時にテーブルを作成
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")

# --- クラスのインスタンス化 ---
state = StateManager()
data_agg = DataAggregator()
analyzer = AnalysisEngine()
trader = TradingExecutor(state)
notifier = TelegramNotifier()
app = Flask(__name__)

# --- メインロジック ---
@app.route('/')
def health_check():
    return f"Auto Trading Bot is {'ACTIVE' if IS_BOT_ACTIVE else 'INACTIVE'}!"

def run_trading_cycle():
    """6時間ごとに実行される取引サイクル"""
    if not IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping trading cycle.")
        return
    if not db_engine:
        logging.error("Database not connected. Skipping trading cycle.")
        return

    logging.info("--- Starting Trading Cycle ---")
    
    # 1. DBから最新の学習済みAIモデルをロード
    latest_model = ml_model.load_latest_model_from_db(db_engine)
    if not latest_model:
        logging.error("No AI model found in DB. Cannot execute trades.")
        return

    # 2. データ収集 -> リスク除外
    all_data = data_agg.get_all_chains_data()
    if all_data.empty: return
    safe_data = risk_filter.filter_risky_tokens(all_data)

    # 3. 分析 (最新モデルを渡す)
    long_df, short_df, spike_df, summary = analyzer.run_analysis(safe_data, latest_model)

    # 4. 通知 & 取引実行
    # ... (前回と同様のロジック)
    logging.info("--- Trading Cycle Finished ---")

def daily_model_retraining_job():
    """深夜に1回だけ実行されるAIモデルの再学習ジョブ"""
    if not db_engine:
        logging.error("Database not connected. Skipping retraining.")
        return
    ml_model.run_daily_retraining(db_engine, data_agg)

def run_scheduler():
    logging.info("Scheduler started.")
    jst = pytz.timezone('Asia/Tokyo')
    
    # 取引サイクルのスケジュール
    schedule.every().day.at("02:00", jst).do(run_trading_cycle)
    schedule.every().day.at("08:00", jst).do(run_trading_cycle)
    schedule.every().day.at("14:00", jst).do(run_trading_cycle)
    schedule.every().day.at("20:00", jst).do(run_trading_cycle)
    
    # ★ 日次AIモデル学習のスケジュールを追加 ★
    schedule.every().day.at("01:00", jst).do(daily_model_retraining_job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
