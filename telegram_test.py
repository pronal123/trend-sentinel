# telegram_test.py
import os
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import Unauthorized, BadRequest

# --- 初期設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# .envファイルから環境変数を読み込む
load_dotenv()

# --- メインのテスト関数 ---
def send_test_notification():
    """Telegramにテスト通知を送信する"""
    
    # 1. 環境変数からキーを読み込む
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    # 2. キーが存在するかチェック
    if not token or not chat_id:
        logging.error("エラー: .envファイルにTELEGRAM_BOT_TOKENまたはTELEGRAM_CHAT_IDが設定されていません。")
        return

    logging.info("テスト通知を送信します...")

    try:
        # 3. ボットを初期化
        bot = Bot(token=token)
        
        # 4. メッセージを作成して送信
        jst = pytz.timezone('Asia/Tokyo')
        now = datetime.now(jst).strftime('%Y/%m/%d %H:%M:%S')
        message = f"✅ テスト通知\n\nこれはBOTからのテストメッセージです。\n({now} JST)"
        
        bot.send_message(chat_id=chat_id, text=message)
        
        logging.info("🎉 テスト通知の送信に成功しました！Telegramを確認してください。")

    except Unauthorized:
        logging.error("エラー: 認証に失敗しました。TELEGRAM_BOT_TOKENが間違っている可能性があります。")
    except BadRequest as e:
        if "Chat not found" in str(e):
            logging.error("エラー: チャットが見つかりません。TELEGRAM_CHAT_IDが間違っているか、BOTがチャットに参加していません。")
        else:
            logging.error(f"エラー: 不正なリクエストです。詳細: {e}")
    except Exception as e:
        logging.error(f"予期せぬエラーが発生しました: {e}")


# --- スクリプトの実行 ---
if __name__ == "__main__":
    send_test_notification()
