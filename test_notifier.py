import os
import sys
import traceback
import ccxt
from telegram_notifier import notify_new_entry, notify_exit, notify_summary

def main():
    print("🚀 テスト開始: Telegram通知 + Bitget残高/ポジション確認")

    try:
        # --- 環境変数チェック ---
        required_envs = [
            "TELEGRAM_TOKEN",
            "TELEGRAM_CHAT_ID",
            "BITGET_API_KEY_SPOT",
            "BITGET_API_SECRET_SPOT",
            "BITGET_API_PASSPHRASE_SPOT",
            "BITGET_API_KEY_FUTURES",
            "BITGET_API_SECRET_FUTURES",
            "BITGET_API_PASSPHRASE_FUTURES",
        ]
        for env in required_envs:
            if not os.getenv(env):
                raise ValueError(f"❌ 環境変数 {env} が未設定です")

        # --- 残高確認 (SPOT) ---
        spot = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY_SPOT"),
            "secret": os.getenv("BITGET_API_SECRET_SPOT"),
            "password": os.getenv("BITGET_API_PASSPHRASE_SPOT"),
        })
        spot_balances = spot.fetch_balance()
        print("💰 SPOT 残高取得成功")

        # --- 残高確認 (FUTURES) ---
        futures = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY_FUTURES"),
            "secret": os.getenv("BITGET_API_SECRET_FUTURES"),
            "password": os.getenv("BITGET_API_PASSPHRASE_FUTURES"),
            "options": {"defaultType": "swap"},
        })
        futures_balances = futures.fetch_balance()
        print("💰 FUTURES 残高取得成功")

        # --- Telegram 通知テスト ---
        notify_summary("✅ Render デプロイ通知テスト: 稼働中です")
        notify_new_entry("BTC/USDT", 0.01, 60000, "テストエントリー")
        notify_exit("BTC/USDT", 0.01, 60500, +50.0, "テスト利確")

        print("✅ テスト完了: 通知を送信しました")

    except Exception as e:
        print("❌ エラー発生:", str(e))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)

if __name__ == "__main__":
    main()
