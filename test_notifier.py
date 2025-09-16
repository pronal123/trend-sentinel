import sys
import types
import os
import ccxt
import requests

# --- imghdr ダミーを挿入 (Python 3.13 対応用) ---
imghdr = types.ModuleType("imghdr")
imghdr.what = lambda *args, **kwargs: None
sys.modules["imghdr"] = imghdr


# --- Telegram 認証情報 ---
telegram_token = os.getenv("TELEGRAM_TOKEN")
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": telegram_chat_id, "text": message}
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        print("📨 テレグラム通知を送信しました！")
    except Exception as e:
        print(f"⚠ Telegram送信失敗: {e}")


# --- Bitget APIキー（SPOTとFUTURES両方） ---
bitget_spot = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_SPOT"),
    "secret": os.getenv("BITGET_API_SECRET_SPOT"),
    "password": os.getenv("BITGET_API_PASSPHRASE_SPOT"),
    "options": {"defaultType": "spot"}
})

bitget_futures = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_FUTURES"),
    "secret": os.getenv("BITGET_API_SECRET_FUTURES"),
    "password": os.getenv("BITGET_API_PASSPHRASE_FUTURES"),
    "options": {"defaultType": "swap"}
})


# --- 残高取得 ---
def fetch_balances():
    spot_balance = None
    futures_balance = None
    try:
        spot_balance = bitget_spot.fetch_balance()
    except Exception as e:
        print(f"⚠ Spot balance fetch error: {e}")

    try:
        futures_balance = bitget_futures.fetch_balance()
    except Exception as e:
        print(f"⚠ Futures balance fetch error: {e}")

    return spot_balance, futures_balance


# --- ポジション取得 ---
def fetch_positions():
    positions = []
    try:
        markets = bitget_futures.load_markets()
        for symbol in markets:
            try:
                pos = bitget_futures.fetch_positions([symbol])
                if pos:
                    positions.extend(pos)
            except Exception:
                continue
    except Exception as e:
        print(f"⚠ Futures positions fetch error: {e}")
    return positions


# --- 通知関数 ---
def notify_summary(extra_message: str = ""):
    spot_balance, futures_balance = fetch_balances()
    positions = fetch_positions()

    message = "✅ Render 稼働チェック\n\n"

    # 現物残高
    if spot_balance:
        message += "💰 Spot 残高 USDT: {}\n".format(
            spot_balance.get("total", {}).get("USDT", "N/A")
        )
    else:
        message += "⚠ Spot 残高取得失敗\n"

    # 先物残高
    if futures_balance:
        message += "📊 Futures 残高 USDT: {}\n".format(
            futures_balance.get("total", {}).get("USDT", "N/A")
        )
    else:
        message += "⚠ Futures 残高取得失敗\n"

    # ポジション
    if positions:
        message += "\n📌 ポジション一覧:\n"
        for p in positions:
            message += "- {}: {} {}\n".format(
                p.get("symbol", "N/A"),
                p.get("side", "N/A"),
                p.get("contracts", "N/A"),
            )
    else:
        message += "\n📌 ポジションなし\n"

    # 追加メッセージ
    if extra_message:
        message = extra_message + "\n\n" + message

    send_telegram_message(message)


# --- 実行部 ---
if __name__ == "__main__":
    notify_summary("✅ Render デプロイ通知テスト: 稼働中です")
