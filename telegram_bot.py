# telegram_bot.py
import aiohttp
import logging
import pytz
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

async def send_telegram_message(session, message):
    """Telegramにメッセージを非同期で送信する内部関数"""
    if not TELEGRAM_BOT_TOKEN or "YOUR_TELEGRAM_BOT_TOKEN" in TELEGRAM_BOT_TOKEN or \
       not TELEGRAM_CHAT_ID or "YOUR_TELEGRAM_CHAT_ID" in TELEGRAM_CHAT_ID:
        logging.warning("Telegram token or chat ID is not set in .env file. Skipping notification.")
        print("\n!!! TelegramのToken/Chat IDが.envファイルに設定されていません。!!!\n")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url, json=payload, timeout=10) as response:
            if response.status != 200:
                logging.error(f"Failed to send Telegram message: Status {response.status} - {await response.text()}")
            else:
                logging.info("Telegram notification sent successfully.")
    except Exception as e:
        logging.error(f"Exception while sending Telegram message: {e}")

async def format_and_send_telegram_notification(longs, shorts, pumps, overview):
    """
    main.pyから呼び出されるメイン関数。
    メッセージを整形し、送信をトリガーする。
    """
    jst = pytz.timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).strftime('%Y/%m/%d %H:%M JST')
    
    message_parts = [f"📡 **トレンドセンチネル速報 ({timestamp})**\n"]

    message_parts.append("--- **📈 LONG候補 (MLスコア順)** ---")
    if longs:
        for token in longs:
            message_parts.append(
                f"銘柄: **{token['baseToken']['symbol']}** ({token['chainId']})\n"
                f"  - 24h: `{token.get('h24', 0):+.2f}%` | 1h: `{token.get('h1', 0):+.2f}%`\n"
                f"  - 出来高(24h): `${token.get('volume_h24', 0):,.0f}`\n"
                f"  - **MLスコア**: `{token.get('surge_probability', 0):.1%}` 🚀"
            )
    else:
        message_parts.append("該当なし")

    message_parts.append("\n--- **📉 SHORT候補 (1h下落順)** ---")
    if shorts:
        for token in shorts:
             message_parts.append(
                f"銘柄: **{token['baseToken']['symbol']}** ({token['chainId']})\n"
                f"  - 24h: `{token.get('h24', 0):.2f}%` | 1h: `{token.get('h1', 0):.2f}%`\n"
                f"  - 出来高(24h): `${token.get('volume_h24', 0):,.0f}`"
            )
    else:
        message_parts.append("該当なし")
    
    message_parts.append("\n--- **📊 市場概況** ---")
    message_parts.append(f"監視銘柄: {overview.get('監視銘柄数', 0)} | 上昇: {overview.get('上昇', 0)} | 下落: {overview.get('下落', 0)}")

    final_message = "\n".join(message_parts)
    
    # aiohttpセッションを作成してメッセージを送信
    async with aiohttp.ClientSession() as session:
        await send_telegram_message(session, final_message)
