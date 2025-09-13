# main.py
import os
import threading
import time
from flask import Flask

# ml_model.pyから、修正した予測開始関数をインポートします
from ml_model import start_model_prediction

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)

@app.route('/')
def health_check():
    """Renderからのヘルスチェックに応答するための関数"""
    return "Machine Learning Bot is alive!"

def model_runner_logic():
    """ml_modelの予測処理を定期的に実行する関数"""
    print("🤖 Background model runner has started.")
    
    while True:
        try:
            # ml_model.pyの予測処理を実行します
            start_model_prediction()
            
            # 次の実行まで待機します (例: 1時間 = 3600秒)
            print("🕒 Waiting for the next run... (1 hour)")
            time.sleep(3600)

        except Exception as e:
            print(f"❌ An error occurred in model_runner_logic: {e}")
            # エラー発生時は5分待機してリトライします
            time.sleep(300)

if __name__ == "__main__":
    # 機械学習モデルをバックグラウンドのスレッドで実行
    model_thread = threading.Thread(target=model_runner_logic)
    model_thread.daemon = True
    model_thread.start()

    # Renderが指定するポートでWebサーバーを起動
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port)
