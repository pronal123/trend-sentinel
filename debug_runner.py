# debug_runner.py (非同期テスト用)
import asyncio
import logging

# --- 初期設定 ---
# main.pyから必要なインスタンスと、テストしたい非同期関数をインポート
from main import state, run_trading_cycle_async

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main_debug():
    """
    BOTのメインサイクルを一度だけ実行して、エラーを特定するための関数
    """
    logging.info("--- Starting BOT in ASYNC Direct Debug Mode ---")
    
    # 状態をファイルから読み込む
    state.load_state_from_disk()
    
    # メインの取引サイクルを一度だけ実行
    await run_trading_cycle_async()
    
    logging.info("--- Debug script finished ---")

# --- スクリプトの実行 ---
if __name__ == "__main__":
    # 非同期関数を実行
    try:
        asyncio.run(main_debug())
    except Exception as e:
        logging.error("An unhandled exception occurred in debug runner:", exc_info=True)
