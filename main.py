# main.py (更新後のフルコード)
import asyncio
import logging
import sys
import os
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from config import DB_FILE, DATABASE_URL, TRAIN_SECRET_KEY
from database import init_db, insert_market_data_batch, update_future_growth_labels
from api_client import fetch_all_data_concurrently
from analyzer import analyze_and_detect_signals
from notifier import format_and_send_telegram_notification
from ml_model import train_model
from trader import execute_trade_logic # ✅ インポート

# (ロガー、Flask、TARGET_PAIRSの設定は変更なし)
# ...

async def analysis_and_alert_job():
    """分析とアラート通知、取引実行を行う非同期ジョブ"""
    logging.info("📡 Starting analysis and alert job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if all_data:
            with create_engine(DATABASE_URL or f"sqlite:///{DB_FILE}").connect() as db_conn:
                with db_conn.begin():
                    longs, shorts, overview = analyze_and_detect_signals(all_data, db_conn)
                
                # ✅ 修正点: 取引ロジックを呼び出す
                execute_trade_logic(longs, shorts, overview)

                if longs or shorts:
                    await format_and_send_telegram_notification(longs, shorts, overview)
                else:
                    logging.info("No significant signals found to notify.")
    except Exception as e:
        logging.critical(f"Error in analysis and alert job: {e}", exc_info=True)

# (その他の関数や起動ロジックは変更なし)
# ...
