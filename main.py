# main.py
import asyncio
import logging
import sqlite3
import sys
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 必要なモジュールを正しくインポート
from config import DB_FILE
from database import init_db, insert_market_data_batch, update_future_growth_labels
from api_client import fetch_all_data_concurrently
from analyzer import analyze_and_detect_signals
from telegram_bot import format_and_send_telegram_notification
from ml_model import train_model

# --- ロガー設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', stream=sys.stdout)

# --- 監視対象のトークンペア ---
TARGET_PAIRS = {
    'ethereum': ['0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640'],
    'solana': ['EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzL7GMKjeRMpzu'],
    'base': ['0x42f2a4866f2bb6f272a81381dfc1a48053b98619'],
    'bsc': ['0x58f876857a02d6762e0101bb5c46a8c1ed44dc16'],
    'arbitrum': ['0xc31e54c7a869b9fcbecc14363cf510d1c41fa441'],
    'optimism': ['0x85149247691df622eac1a890620f5c276d48e269'],
    'polygon': ['0xa374094527e1673a86de625aa59517c5de346d32'],
    'avalanche': ['0xf4003f4efbe8691862452f05301293b06024b46f']
}

async def data_collection_job():
    """ML用データを収集・整形するジョブ"""
    logging.info("🔬 Starting data collection job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if not all_data:
            logging.info("No data fetched in collection job.")
            return
        with sqlite3.connect(DB_FILE, timeout=10) as db_conn:
            update_future_growth_labels(db_conn, all_data)
            insert_market_data_batch(db_conn, all_data)
    except Exception as e:
        logging.critical(f"Error in data collection job: {e}", exc_info=True)

async def analysis_and_alert_job():
    """分析とアラート通知を行うジョブ"""
    logging.info("📡 Starting analysis and alert job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if not all_data:
            logging.info("No data fetched in analysis job.")
            return
        with sqlite3.connect(DB_FILE, timeout=10) as db_conn:
            longs, shorts, pumps, overview = analyze_and_detect_signals(all_data, db_conn)
            if longs or shorts:
                await format_and_send_telegram_notification(longs, shorts, pumps, overview)
            else:
                logging.info("No significant signals found to notify.")
    except Exception as e:
        logging.critical(f"Error in analysis and alert job: {e}", exc_info=True)

async def main(mode=None):
    """アプリケーションの初期化とスケジューラの起動"""
    init_db()
    
    if mode == "train":
        train_model()
        return

    scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(data_collection_job, 'cron', minute='*/15')
    scheduler.add_job(analysis_and_alert_job, 'cron', hour='2,8,14,20', minute='5')
    scheduler.start()
    logging.info("Scheduler started. Waiting for jobs... Press Ctrl+C to exit.")
    
    logging.info("Running initial jobs immediately after startup...")
    await data_collection_job()
    await analysis_and_alert_job()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logging.info("Scheduler shut down.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "train":
        print("Running in training mode...")
        main(mode="train")
    else:
        asyncio.run(main())
