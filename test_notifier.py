import os
import ccxt
import logging
from telegram import Bot
import asyncio

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Telegram BOT ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TELEGRAM_TOKEN)

# --- Bitget 現物 API ---
bitget_spot = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_SPOT"),
    "secret": os.getenv("BITGET_API_SECRET_SPOT"),
    "password": os.getenv("BITGET_API_PASSPHRASE_SPOT"),
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

# --- Bitget 先物 API ---
bitget_futures = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_FUTURES"),
    "secret": os.getenv("BITGET_API_SECRET_FUTURES"),
    "password": os.getenv("BITGET_API_PASSPHRASE_FUTURES"),
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}  # 永続先物
})


async def main():
    logging.info("=== Bitget Spot / Futures API & Telegram Notification Test ===")

    try:
        # --- 現物残高 ---
        spot_balance = bitget_spot.fetch_balance({'type': 'spot'})
        spot_summary = {k: v for k, v in spot_balance['total'].items() if v > 0}

        # --- 先物残高 ---
        futures_balance = bitget_futures.fetch_balance({'type': 'future'})
        futures_summary = {k: v for k, v in futures_balance['total'].items() if v > 0}

        # --- 先物ポジション ---
        futures_positions = bitget_futures.fetch_positions()
        open_positions = [p for p in futures_positions if float(p.get("contracts", 0)) > 0]

        # --- 通知メッセージ作成 ---
        msg = "✅ *Bitget API / Telegram Test 成功*\n\n"

        msg += "📊 *Spot 残高:*\n"
        if spot_summary:
            for coin, amount in spot_summary.items():
                msg += f"- {coin}: {amount}\n"
        else:
            msg += "- 保有なし\n"

        msg += "\n📊 *Futures 残高:*\n"
        if futures_summary:
            for coin, amount in futures_summary.items():
                msg += f"- {coin}: {amount}\n"
        else:
            msg += "- 保有なし\n"

        msg += "\n📈 *Futures ポジション:*\n"
        if open_positions:
            for pos in open_positions:
                msg += (
                    f"- {pos['symbol']} | {pos['side']} | "
                    f"契約数: {pos['contracts']} | 未実現PnL: {pos['unrealizedPnl']}\n"
                )
        else:
            msg += "- ポジションなし\n"

        # --- Telegram 通知 ---
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        logging.info("✅ Telegram通知を送信しました")

    except Exception as e:
        logging.error(f"❌ エラー: {e}")


if __name__ == "__main__":
    asyncio.run(main())
