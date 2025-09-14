# debug_runner.py
import logging

# --------------------------------------------------------------------
# 最初に必要なモジュールをインポートする
# main.py内の全てのグローバル変数が初期化されるようにするため
# --------------------------------------------------------------------
try:
    from main import run_trading_cycle
    print("✅ Successfully imported 'run_trading_cycle' from main.py")
except ImportError as e:
    print(f"❌ Failed to import 'run_trading_cycle'. Error: {e}")
    print("Please ensure main.py and all its dependencies are correct.")
    exit()
except Exception as e:
    print(f"An unexpected error occurred during import: {e}")
    exit()

# --------------------------------------------------------------------
# メインの実行部分
# --------------------------------------------------------------------
if __name__ == "__main__":
    # ログ設定をここでも行うと、実行中の詳細が表示されて便利
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    logging.info("--- Starting a single debug run of the trading cycle ---")
    
    # メインの取引サイクル関数を1回だけ呼び出す
    run_trading_cycle()
    
    logging.info("--- Debug run finished ---")
