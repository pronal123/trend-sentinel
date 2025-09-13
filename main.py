# main.py
import os
import threading
import time
import logging
from flask import Flask

# 他のファイルから必要な関数をインポート
import ml_model
import trading

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)

@app.route('/')
def health_check():
    """Renderからのヘルスチェックに応答"""
    return "Trading Bot Service is alive and running!"

def bot_runner_logic():
    """BOTのメインロジック。分析と取引を定期的に実行する"""
    logging.info("🤖 Trading Bot runner has started in the background.")
    
    # 取引所APIを初期化
    trading.initialize_api()
    
    while True:
        try:
            # 1. 分析モジュールから売買シグナルを取得
            signal = ml_model.start_model_analysis(ticker='^N225', period='1y')
            
            # 2. シグナルに基づいて行動を決定
            if signal == 'BUY':
                # TODO: 実際の取引ロジックに合わせて、購入金額やリスク管理を設定
                trading.execute_buy_order(ticker='^N225', amount_jpy=50000) # 例: 5万円分購入
            
            elif signal == 'SELL':
                # TODO: 現在保有しているポジションを売却するロジックを実装
                trading.execute_sell_order(ticker='^N225', position_size='all') # 例: 全て売却
            
            else: # HOLD
                logging.info("Signal is 'HOLD'. No action taken.")

            # 3. 次の実行まで待機 (例: 1時間)
            logging.info("🕒 Waiting for the next cycle... (1 hour)")
            time.sleep(3600)

        except Exception as e:
            logging.error(f"❌ An error occurred in the main bot loop: {e}")
            time.sleep(300) # エラー発生時は5分待機

if __name__ == "__main__":
    # BOTロジックをバックグラウンドのスレッドで実行
    bot_thread = threading.Thread(target=bot_runner_logic)
    bot_thread.daemon = True
    bot_thread.start()

    # Renderが指定するポートでWebサーバーを起動
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"🌐 Starting web server on port {port}...")
    
    # 本番環境ではGunicornが使われるため、app.run()はデバッグ用
    # RenderのStart CommandでGunicornを起動する
    # gunicorn --bind 0.0.0.0:$PORT main:app
    app.run(host='0.0.0.0', port=port)
