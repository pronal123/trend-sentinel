# debug_runner.py

import logging

# main.pyからBOTのメインロジック関数をインポート
from main import bot_runner_logic

# ログ設定をここでも行う
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

print("--- Starting BOT in Direct Debug Mode ---")
logging.info("--- Starting BOT in Direct Debug Mode ---")

# BOTのメインロジックを直接実行する
# これでクラッシュすれば、その原因がログの最後に出力されるはず
bot_runner_logic()

print("--- Debug script finished ---")
logging.info("--- Debug script finished ---")

