# main.py (修正例 - 適切な場所にinit_db()を追加)

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import asyncio
from analyzer import analyze_and_notify
from telegram_bot import setup_bot
from database import init_db # ✅ インポート

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Telegramボットのセットアップ
bot = setup_bot()

def main():
    logging.info("Service started. Setting up scheduler...")
    init_db() # ✅ ここで明示的にDBを初期化

    scheduler = BlockingScheduler()
    # 毎分分析ジョブを実行
    scheduler.add_job(lambda: asyncio.run(analyze_and_notify(bot)), 'interval', minutes=1)
    
    # AIモデルの再学習ジョブ (オプション)
    # scheduler.add_job(lambda: asyncio.run(train_model_job()), 'interval', hours=24) # 例: 毎日実行

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
