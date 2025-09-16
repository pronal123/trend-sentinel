import sys
import traceback

def main():
    try:
        import time
        import ccxt
        import os
        from telegram_notifier import notify_new_entry, notify_exit, notify_summary
        from telegram.error import TelegramError

        print("🚀 Telegram通知 + Bitget SPOT/FUTURES テスト開始")

        # 残高・ポジション通知
        from test_notifier import format_balance_report, notify_summary, notify_new_entry, notify_exit
        notify_summary("✅ Render デプロイ後の通知テストです")
        time.sleep(2)

        notify_new_entry("BTC/USDT", 0.01, 60000, "テスト")
        time.sleep(2)

        notify_exit("BTC/USDT", 0.01, 60500, +50.0, "テスト利確")

        print("✅ テスト通知を送信しました")

    except Exception as e:
        print("❌ エラー発生:", str(e))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
