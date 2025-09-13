# main.py
import os
import threading
import time
import logging
from flask import Flask

import ml_model
from trading import TradingBot # クラスをインポート

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Trading Bot Service is alive and running!"

def bot_runner_logic():
    logging.info("🤖 Trading Bot runner has started in the background.")
    
    # TradingBotクラスのインスタンスを作成
    # TODO: 取引したいティッカーや金額をここで設定
    bot = TradingBot(ticker='BTC/USDT', trade_amount_usd=100.0)
    
    while True:
        try:
            # 1. 分析モジュールから売買シグナルを取得
            # 取引ペアに合わせてティッカーを渡す
            yf_ticker = bot.ticker.replace('/','-') # yfinance用のティッカー形式に変換
            signal = ml_model.start_model_analysis(ticker=yf_ticker, period='1y')
            
            # 2. シグナルに基づいてBOTのメソッドを呼び出す
            if signal == 'BUY':
                bot.execute_buy_order()
            
            elif signal == 'SELL':
                bot.execute_sell_order()
            
            else: # HOLD
                logging.info("Signal is 'HOLD'. No action taken.")

            # 3. 次の実行まで待機
            logging.info("🕒 Waiting for the next cycle... (1 hour)")
            time.sleep(3600)

        except Exception as e:
            logging.error(f"❌ An error occurred in the main bot loop: {e}")
            time.sleep(300)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=bot_runner_logic)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 8080))
    logging.info(f"🌐 Starting web server on port {port}...")
    # 本番環境ではGunicornが使われる
    app.run(host='0.0.0.0', port=port)
