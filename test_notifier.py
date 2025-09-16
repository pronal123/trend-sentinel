import time
import ccxt
import os
from telegram_notifier import notify_new_entry, notify_exit, notify_summary, bot, TELEGRAM_CHAT_ID

# ==============================
# Bitget SPOT 設定
# ==============================
bitget_spot = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_SPOT"),
    "secret": os.getenv("BITGET_API_SECRET_SPOT"),
    "password": os.getenv("BITGET_API_PASSPHRASE_SPOT"),
    "options": {"defaultType": "spot"},
})

# ==============================
# Bitget FUTURES 設定
# ==============================
bitget_futures = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_FUTURES"),
    "secret": os.getenv("BITGET_API_SECRET_FUTURES"),
    "password": os.getenv("BITGET_API_PASSPHRASE_FUTURES"),
    "options": {"defaultType": "swap"},
})


def fetch_bitget_status():
    """現物と先物の残高・ポジションを取得"""
    results = {}

    # --- 現物 ---
    try:
        balance_spot = bitget_spot.fetch_balance()
        results["spot_balance"] = balance_spot
    except Exception as e:
        results["spot_balance"] = f"❌ SPOT API Error: {str(e)}"

    # --- 先物 ---
    try:
        balance_futures = bitget_futures.fetch_balance(params={"type": "swap"})
        positions_futures = bitget_futures.fetch_positions()
        results["futures_balance"] = balance_futures
        results["futures_positions"] = positions_futures
    except Exception as e:
        results["futures_balance"] = f"❌ FUTURES API Error: {str(e)}"
        results["futures_positions"] = []

    return results


def send_balance_report():
    """Telegramに現物/先物残高・ポジションを送信"""
    status = fetch_bitget_status()

    msg = "📊 *Bitget 現物・先物残高/ポジション レポート*\n\n"

    # 現物
    msg += "💰 *SPOT 残高*\n"
    if isinstance(status["spot_balance"], dict):
        for coin, bal in status["spot_balance"]["total"].items():
            if bal and bal > 0:
                msg += f"- {coin}: {bal}\n"
    else:
        msg += f"{status['spot_balance']}\n"

    msg += "\n📈 *FUTURES 残高*\n"
    if isinstance(status["futures_balance"], dict):
        usdt = status["futures_balance"].get("total", {}).get("USDT", 0)
        msg += f"- USDT: {usdt}\n"
    else:
        msg += f"{status['futures_balance']}\n"

    msg += "\n📌 *FUTURES ポジション*\n"
    if status["futures_positions"]:
        for pos in status["futures_positions"]:
            if float(pos["contracts"]) > 0:
                symbol = pos["symbol"]
                side = pos["side"]
                size = pos["contracts"]
                entry = pos["entryPrice"]
                unreal = pos["unrealizedPnl"]
                msg += f"- {symbol} {side} {size} @ {entry}, PnL: {unreal}\n"
    else:
        msg += "なし\n"

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")


if __name__ == "__main__":
    print("🚀 Telegram通知 + Bitget SPOT/FUTURES テスト開始")

    # 1. 残高・ポジション通知
    send_balance_report()
    time.sleep(2)

    # 2. 新規エントリー通知
    notify_new_entry(symbol="BTC/USDT", size=0.01, price=60000, reason="テストエントリー")
    time.sleep(2)

    # 3. 決済通知
    notify_exit(symbol="BTC/USDT", size=0.01, price=60500, pnl=+50.0, reason="テスト利確")
    time.sleep(2)

    # 4. サマリー通知
    notify_summary()
    time.sleep(2)

    # 5. 日次損益リセット通知
    reset_daily_pnl()

    print("\n✅ テスト通知を送信しました")
