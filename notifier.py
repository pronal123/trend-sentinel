import aiohttp
import logging
import pytz
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

async def send_telegram_message(session, message):
    """Sends a message to Telegram asynchronously."""
    if not TELEGRAM_BOT_TOKEN or "YOUR_TELEGRAM" in TELEGRAM_BOT_TOKEN:
        logging.warning("Telegram token/chat ID not set. Skipping notification.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        async with session.post(url, json=payload, timeout=10) as response:
            if response.status != 200:
                logging.error(f"Failed to send Telegram message: {await response.text()}")
            else:
                logging.info("Telegram notification sent successfully.")
    except Exception as e:
        logging.error(f"Exception while sending Telegram message: {e}")

async def format_and_send_notification(data, notification_type='signal'):
    """Formats and sends notifications based on type ('signal' or 'trade')."""
    
    message_lines = []
    
    if notification_type == 'signal':
        longs, shorts, overview = data
        jst = pytz.timezone('Asia/Tokyo')
        timestamp = datetime.now(jst).strftime('%Y/%m/%d %H:%M JST')
        
        message_lines.append(f"📡 **トレンドセンチネル速報 ({timestamp})**\n")
        message_lines.append("--- **📈 LONG候補 (AIスコア順)** ---")
        if longs:
            for token in longs:
                message_lines.append(f"銘柄: **{token['baseToken']['symbol']}** ({token['chainId']})\n  - 上昇スコア: `{token.get('surge_probability', 0):.1%}` 🚀")
        else:
            message_lines.append("該当なし")

        message_lines.append("\n--- **📉 SHORT候補 (AIスコア順)** ---")
        if shorts:
            for token in shorts:
                message_lines.append(f"銘柄: **{token['baseToken']['symbol']}** ({token['chainId']})\n  - 下落スコア: `{token.get('dump_probability', 0):.1%}` 💥")
        else:
            message_lines.append("該当なし")
        
        message_lines.append(f"\n--- **📊 市場概況** ---\n監視銘柄: {overview.get('監視銘柄数', 0)}")

    elif notification_type == 'trade':
        trade_info = data
        trade_event = trade_info.get('type')
        symbol = trade_info.get('symbol')
        
        if trade_event == 'open':
            side, amount, entry_price = trade_info.get('side'), trade_info.get('amount'), trade_info.get('entry_price')
            pos_val, sl, tp, bal = amount * entry_price, trade_info.get('sl_price'), trade_info.get('tp_price'), trade_info.get('balance')
            icon = "📈" if side == 'long' else "📉"
            message_lines.extend([
                f"**{icon} 新規{side.upper()}ポジション**", f"**銘柄:** {symbol}",
                f"**ポジション額:** ${pos_val:,.2f}", f"**平均取得価格:** ${entry_price:,.4f}", "---",
                f"**利確ポイント:** ${tp:,.4f}", f"**損切ポイント:** ${sl:,.4f}", "---",
                f"**現在の口座残高:** ${bal:,.2f}"
            ])
        elif trade_event == 'close':
            pnl, pnl_pct, bal = trade_info.get('pnl'), trade_info.get('pnl_percent'), trade_info.get('balance')
            icon = "✅" if pnl >= 0 else "❌"
            message_lines.extend([
                f"**{icon} ポジション決済**", f"**銘柄:** {symbol}",
                f"**損益額:** **${pnl:,.2f} ({pnl_pct:+.2f}%)**", "---",
                f"**現在の口座残高:** ${bal:,.2f}", "**保有ポジション:** なし"
            ])

    if not message_lines:
        return

    final_message = "\n".join(message_lines)
    async with aiohttp.ClientSession() as session:
        await send_telegram_message(session, final_message)

