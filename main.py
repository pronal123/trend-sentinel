import asyncio
import logging
import sqlite3
import sys
import os
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import OperationalError

from config import DB_FILE, DATABASE_URL, TRAIN_SECRET_KEY
from database import init_db, insert_market_data_batch, update_future_growth_labels, engine
from api_client import fetch_all_data_concurrently
from analyzer import analyze_and_detect_signals
from notifier import format_and_send_telegram_notification
from ml_model import train_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', stream=sys.stdout)
app = Flask(__name__)

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
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if all_data:
            with engine.connect() as db_conn:
                with db_conn.begin(): # トランザクションを開始
                    insert_market_data_batch(db_conn, all_data)
                    update_future_growth_labels(db_conn)
    except OperationalError as e:
        logging.error(f"Database connection failed: {e}")
    except Exception as e:
        logging.critical(f"Error in data collection job: {e}", exc_info=True)

async def analysis_and_alert_job():
    logging.info("📡 Starting analysis and alert job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if all_data:
            with engine.connect() as db_conn:
                with db_conn.begin():
                    longs, shorts, overview = analyze_and_detect_signals(all_data, db_conn)
                if longs or shorts:
                    await format_and_send_telegram_notification(longs, shorts, overview)
                else:
                    logging.info("No significant signals found to notify.")
    except OperationalError as e:
        logging.error(f"Database connection failed: {e}")
    except Exception as e:
        logging.critical(f"Error in analysis and alert job: {e}", exc_info=True)

# --- スケジューラ用の同期ラッパー ---
def run_async_job(job_func):
    asyncio.run(job_func())

def data_collection_wrapper(): run_async_job(data_collection_job)
def analysis_and_alert_wrapper(): run_async_job(analysis_and_alert_job)

# --- Webサーバーのエンドポイント定義 ---
@app.route('/')
def home():
    return "✅ Trend Sentinel is running."

@app.route('/train')
def trigger_training():
    """モデル学習をトリガーするWebエンドポイント"""
    secret_key = request.args.get('secret')
    if not TRAIN_SECRET_KEY or secret_key != TRAIN_SECRET_KEY:
        return "🚫 Unauthorized", 401
    
    try:
        logging.info("Manual training triggered via webhook.")
        train_model()
        return "✅ Training process started successfully.", 200
    except Exception as e:
        logging.error(f"Failed to start training: {e}")
        return f"🔥 Error starting training: {e}", 500

# --- メインの起動処理 ---
def start_scheduler():
    init_db()
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(data_collection_wrapper, 'cron', minute='*/15')
    scheduler.add_job(analysis_and_alert_wrapper, 'cron', hour='2,8,14,20', minute=2)
    scheduler.start()
    logging.info("Scheduler started in background.")
    data_collection_wrapper()

# Gunicornから起動される際にスケジューラを開始
if __name__ != '__main__':
    start_scheduler()
