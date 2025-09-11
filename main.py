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
        logging.critical(f"Error in data collection job: {e}", exc_info=True)

async def analysis_and_alert_job():
    """分析とアラート通知を行う非同期ジョ-ブ"""
    logging.info("📡 Starting analysis and alert job...")
    try:
        all_data = await fetch_all_data_concurrently(TARGET_PAIRS)
        if all_data:
            with sqlite3.connect(DB_FILE, timeout=10) as db_conn:
                longs, shorts, overview = analyze_and_detect_signals(all_data, db_conn)
                if longs or shorts:
                    await format_and_send_telegram_notification(longs, shorts, overview)
                else:
                    logging.info("No significant signals found to notify.")
    except Exception as e:
        logging.critical(f"Error in analysis and alert job: {e}", exc_info=True)

# --- スケジューラ用の同期ラッパー関数 ---
def run_async_job(job_func):
    """非同期関数を同期的に実行するためのラッパー"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 既に実行中のループがあれば、タスクとして投入
            asyncio.ensure_future(job_func())
        else:
            # ループがなければ、新規に実行
            asyncio.run(job_func())
    except RuntimeError:
        # 'RuntimeError: Cannot run the event loop while another loop is running' 対策
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(job_func())

def data_collection_wrapper():
    run_async_job(data_collection_job)

def analysis_and_alert_wrapper():
    run_async_job(analysis_and_alert_job)

# --- Webサーバーのエンドポイント定義 ---
@app.route('/')
def home():
    """Renderのヘルスチェック用エンドポイント"""
    return "✅ Trend Sentinel is running."

# --- メインの起動処理 ---
def start_scheduler():
    """スケジューラの初期化とジョブの登録"""
    # データベースを初期化
    init_db()
    
    # バックグラウンドで動作するスケジューラを使用
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    
    # スケジュールを登録
    # 毎時1分にデータ収集ジョブを実行
    scheduler.add_job(data_collection_wrapper, 'cron', minute=1)
    # JST 02:02, 08:02, 14:02, 20:02に分析ジョブを実行
    scheduler.add_job(analysis_and_alert_wrapper, 'cron', hour='2,8,14,20', minute=2)
    
    scheduler.start()
    logging.info("Scheduler started in background.")

    # 起動時に初回ジョブを手動で実行
    logging.info("Running initial jobs immediately after startup...")
    data_collection_wrapper()
    analysis_and_alert_wrapper()


# このifブロックは、Gunicornから起動される際に重要
if __name__ == '__main__':
    # モデル学習モードの判定
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'train':
        print("Running in training mode...")
        init_db() # 学習前にもDBを確実に初期化
        train_model()
    else:
        # 通常のWebサーバーモード
        start_scheduler()
        # このファイルが直接実行された場合（ローカルテスト用）
        # Render環境ではGunicornがappを起動するため、このrunは実行されない
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
else:
    # Gunicornからインポートされた場合にスケジューラを起動
    start_scheduler()