import asyncio
import logging
import sqlite3
import sys
import os
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# プロジェクト内の他モジュールをインポート
from config import DB_FILE
from database import init_db, insert_market_data_batch, update_future_growth_labels
from api_client import fetch_all_data_concurrently
from analyzer import analyze_and_detect_signals
from notifier import format_and_send_telegram_notification
from ml_model import train_model

# --- ロガー設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', stream=sys.stdout)

# --- Flaskアプリケーションの初期化 ---
app = Flask(__name__)

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

# --- 非同期ジョブの定義 ---
async def data_collection_job():
    """ML用データを収集・整形する非同期ジョブ"""
    logging.info("🔬 Starting data collection job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if all_data:
            with sqlite3.connect(DB_FILE, timeout=10) as db_conn:
                update_future_growth_labels(db_conn, all_data)
                insert_market_data_batch(db_conn, all_data)
    except Exception as e:
        logging.critical(f"
