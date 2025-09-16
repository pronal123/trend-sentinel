import os
import ccxt
import requests
from datetime import datetime, timezone, timedelta

# --------------------
# 環境変数の取得
# --------------------
BITGET_API_KEY = os.getenv("BITGET_API_KEY_FUTURES", "")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET_FUTURES", "")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE_FUTURES", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --------------------
# Telegram送信関数
# --------------------
def send_telegram_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("環境変数 TELEGRAM_TOKEN / TELEGRAM_CHAT_ID が未設定です")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

# --------------------
# JSTの現在時刻
# --------------------
def now_jst():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))

# --------------------
# メイン処理
# --------------------
if __name__ == "__main__":
    print("=== 環境変数チェック ===")
    print("BITGET_API_KEY:", "OK" if BITGET_API_KEY else "MISSING")
    print("BITGET_API_SECRET:", "OK" if BITGET_API_SECRET else "MISSING")
    print("BITGET_API_PASSPHRASE:", "OK" if BITGET_API_PASSPHRASE else "MISSING")
    print("TELEGRAM_TOKEN:", "OK" if TELEGRAM_TOKEN else "MISSING")
    print("TELEGRAM_CHAT_ID:", "OK" if TELEGRAM_CHAT_ID else "MISSING")

    # Bitget クライアント作成
    exchange = None
    try:
        exchange = ccxt.bitget({
            "apiKey": BITGET_API_KEY,
            "secret": BITGET_API_SECRET,
            "password": BITGET_API_PASSPHRASE,
            "enableRateLimit": True,
        })
        print("\n✅ Bitgetクライアント作成成功")
    except Exception as e:
        print("\n❌ Bitgetクライアント作成失敗:", e)

    # 残高・ポジション確認
    if exchange:
        try:
            spot_balance = exchange.fetch_balance({"type": "spot"})
            futures_balance = exchange.fetch_balance({"type": "swap"})
            positions = exchange.fetch_positions()

            print("\n✅ Bitget API呼び出し成功")
            print("【現物残高】USDT:", spot_balance.get("total", {}).get("USDT", "N/A"))
            print("【先物残高】USDT:", futures_balance.get("total", {}).get("USDT", "N/A"))
            print("ポジション数:", len(positions))
        except Exception as e:
            print("\n❌ Bitget APIエラー:", e)

    # Telegram送信テスト
    try:
        msg = (
            f"🚀 テスト通知\n"
            f"時刻: {now_jst().strftime('%Y-%m-%d %H:%M:%S JST')}\n"
            f"現物USDT残高: {spot_balance.get('total', {}).get('USDT', 'N/A')}\n"
            f"先物USDT残高: {futures_balance.get('total', {}).get('USDT', 'N/A')}\n"
            f"ポジション数: {len(positions)}"
        )
        result = send_telegram_message(msg)
        print("\n✅ Telegram送信成功:", result)
    except Exception as e:
        print("\n❌ Telegram送信エラー:", e)
