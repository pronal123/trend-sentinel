from flask import Flask, request, jsonify
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import asyncio
import os

# プロジェクト内の他モジュールをインポート
from analyzer import analyze_and_notify
from telegram_bot import setup_bot, bot_app # bot_appをインポート
from database import init_db, DATABASE_URL
from ml_model import train_model
from config import TRAIN_SECRET_KEY, MODEL_PATH

# ロギング設定 (ここを最初に設定することで、全てのモジュールに適用される)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
bot = setup_bot() # Telegramボットを初期化

# APSchedulerの初期化 (ここではBlockingSchedulerを使用)
scheduler = BlockingScheduler(timezone="UTC")

# --- Flaskルート ---

@app.route('/')
def health_check():
    """Renderのヘルスチェック用ルート"""
    return "Service is running!", 200

@app.route('/train_model', methods=['POST'])
def train_model_endpoint():
    """
    AIモデルの再学習をトリガーするAPIエンドポイント。
    セキュリティのため、シークレットキーで保護されている。
    """
    if not request.is_json:
        return jsonify({"message": "Request must be JSON"}), 400

    data = request.get_json()
    secret_key = data.get('secret_key')

    if secret_key != TRAIN_SECRET_KEY:
        logging.warning("Unauthorized attempt to trigger model training.")
        return jsonify({"message": "Unauthorized"}), 401

    logging.info("Model training triggered via API.")
    # 非同期処理として学習を実行
    asyncio.run_coroutine_threadsafe(train_model_job_async(), asyncio.get_event_loop())
    
    return jsonify({"message": "Model training started in background."}), 202

# --- Scheduler Jobs ---

async def analyze_and_notify_job():
    """分析と通知のジョブ"""
    logging.info("Running analysis and notification job...")
    try:
        await analyze_and_notify(bot)
    except Exception as e:
        logging.error(f"Error during analysis and notification job: {e}", exc_info=True)

async def train_model_job_async():
    """AIモデルの再学習ジョブ (非同期)"""
    if not DATABASE_URL:
        logging.warning("DATABASE_URL not set. Skipping AI model training.")
        return

    logging.info("Starting AI model training job...")
    try:
        train_model(db_path=DATABASE_URL, model_path=MODEL_PATH)
        logging.info("AI model training completed.")
    except Exception as e:
        logging.error(f"Error during AI model training: {e}", exc_info=True)


# --- Main Execution ---
def main():
    logging.info("Service started. Initializing database and setting up scheduler...")
    init_db() # ✅ データベースの初期化を明示的に呼び出す

    # 分析ジョブをスケジューリング
    scheduler.add_job(
        analyze_and_notify_job, # 非同期関数を直接指定
        'interval',
        minutes=1,
        id='analysis_job',
        next_run_time=None # 起動時にすぐ実行する代わりに、初回の実行をスケジュールに任せる
    )
    logging.info("Analysis job scheduled to run every 1 minute.")

    # AIモデルの再学習ジョブをスケジューリング (例: 毎日午前0時に実行)
    if TRAIN_SECRET_KEY: # TRAIN_SECRET_KEYが設定されている場合のみ学習ジョブをスケジューリング
        scheduler.add_job(
            train_model_job_async, # 非同期関数を直接指定
            'cron',
            hour=0, # UTCの午前0時
            id='model_training_job'
        )
        logging.info("AI model training job scheduled daily at 00:00 UTC.")
    else:
        logging.warning("TRAIN_SECRET_KEY not set. Skipping daily AI model training job.")

    # スケジューラーを開始
    scheduler.start()
    logging.info("Scheduler started.")

    # Telegram Webhookを設定 (Renderのような環境では必須)
    if TELEGRAM_BOT_TOKEN := os.getenv("TELEGRAM_BOT_TOKEN"):
        WEBHOOK_URL = f"https://trend-sentinel.onrender.com/webhook/{TELEGRAM_BOT_TOKEN}" # あなたのRender URLに合わせて変更
        asyncio.run(bot.set_webhook(url=WEBHOOK_URL))
        logging.info(f"Telegram webhook set to: {WEBHOOK_URL}")
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))) # Flaskアプリを起動
    else:
        logging.critical("TELEGRAM_BOT_TOKEN is not set. Cannot run Flask app or set webhook.")
        # WebhookなしでAPSchedulerのみを実行する場合 (テスト用)
        # try:
        #    while True:
        #        asyncio.run(asyncio.sleep(1)) # スケジューラがバックグラウンドで動くように維持
        # except (KeyboardInterrupt, SystemExit):
        #    scheduler.shutdown()


# Flaskアプリが直接実行された場合
if __name__ == "__main__":
    # main()関数を実行
    main()
