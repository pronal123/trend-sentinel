import asyncio
import logging
import sys
import os
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine

# プロジェクト内の他モジュールをインポート
from config import DB_FILE, DATABASE_URL, TRAIN_SECRET_KEY
from database import init_db
from api_client import fetch_all_data_concurrently
from analyzer import analyze_and_detect_signals
from ml_model import train_model
from trader import execute_trade_logic
# ✅ 修正点: 統一された通知関数をインポート
from notifier import format_and_send_notification

# --- ロガー設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', stream=sys.stdout)

# --- Flaskアプリケーションの初期化 ---
app = Flask(__name__)

# --- 監視対象のトークンペア ---
TARGET_PAIRS = {
    'ethereum': ['0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'], 'solana': ['EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzL7GMKjeRMpzu'],
    'base': ['0x42f2a4866f2bb6f272a81381dfc1a48053b98619'], 'bsc': ['0x58f876857a02d6762e0101bb5c46a8c1ed44dc16'],
    'arbitrum': ['0xc31e54c7a869b9fcbecc14363cf510d1c41fa441'], 'optimism': ['0x85149247691df622eac1a890620f5c276d48e269'],
    'polygon': ['0xa374094527e1673a86de625aa59517c5de346d32'], 'avalanche': ['0xf4003f4efbe8691862452f05301293b06024b46f']
}

# --- 非同期ジョブの定義 ---
async def data_collection_job():
    logging.info("🔬 Starting data collection job...")
    try:
        # データ収集自体はapi_clientで行い、結果はDBに保存される
        await fetch_all_data_concurrently(TARGET_PAIRS)
    except Exception as e:
        logging.critical(f"Error in data collection job: {e}", exc_info=True)

async def analysis_and_alert_job():
    """分析、通知、取引実行を統括する非同期ジョブ"""
    logging.info("📡 Starting analysis and alert job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if all_data:
            # DBエンジンを直接使用
            engine = create_engine(DATABASE_URL or f"sqlite:///{DB_FILE}")
            with engine.connect() as db_conn:
                with db_conn.begin():
                    longs, shorts, all_indicators, overview = analyze_and_detect_signals(all_data, db_conn)
                
                # 取引ロジックは自身の通知機能を持つ
                execute_trade_logic(longs, shorts, all_indicators)

                # シグナル通知（取引とは別）
                notification_longs = longs[:3] if longs else []
                notification_shorts = shorts[:3] if shorts else []
                if notification_longs or notification_shorts:
                    # ✅ 修正点: 統一された関数を正しく呼び出す
                    await format_and_send_notification(
                        (notification_longs, notification_shorts, overview), 
                        notification_type='signal'
                    )
                else:
                    logging.info("No significant signals found to notify.")
    except Exception as e:
        logging.critical(f"Error in analysis and alert job: {e}", exc_info=True)

# --- スケジューラ用の同期ラッパー ---
def run_async_job(job_func):
    try:
        asyncio.run(job_func())
    except RuntimeError:
        # 既にイベントループが実行中の場合のフォールバック
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(job_func())
        else:
             asyncio.run(job_func())

def data_collection_wrapper(): run_async_job(data_collection_job)
def analysis_and_alert_wrapper(): run_async_job(analysis_and_alert_job)

# --- Webサーバーのエンドポイント定義 ---
@app.route('/')
def home():
    return "✅ Trend Sentinel is running."

@app.route('/train')
def trigger_training():
    secret_key = request.args.get('secret')
    if not TRAIN_SECRET_KEY or secret_key != TRAIN_SECRET_KEY:
        return "🚫 Unauthorized", 401
    try:
        logging.info("Manual training triggered via webhook.")
        train_model()
        return "✅ Training process started successfully.", 200
    except Exception as e:
        error_message = str(e)
        logging.error(f"Failed to start training: {error_message}")
        return f"🔥 Error starting training: {error_message}", 500

# --- メインの起動処理 ---
def start_scheduler():
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(data_collection_wrapper, 'cron', minute='*/15')
    scheduler.add_job(analysis_and_alert_wrapper, 'cron', hour='2,8,14,20', minute=2)
    scheduler.start()
    logging.info("Scheduler started in background.")
    # 起動時の初回ジョブ
    data_collection_wrapper()

if __name__ == '__main__':
    # コマンドラインから 'train' が指定された場合の処理
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'train':
        init_db()
        train_model()
    else:
        # 通常のWebサーバーモード
        start_scheduler()
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
else:
    # Gunicornからインポートされた場合にスケジューラを起動
    start_scheduler()
