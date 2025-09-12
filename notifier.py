import aiohttp
import logging
import pytz
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# (send_telegram_message, format_and_send_telegram_notification は変更なし)
# ...

# ✅ 修正点: 取引実行用の通知関数を新設
async def format_and_send_trade_notification(trade_info):
    """取引の実行結果を詳細に通知する"""
    if not TELEGRAM_BOT_TOKEN or "YOUR_TELEGRAM" in TELEGRAM_BOT_TOKEN:
        return

    trade_type = trade_info.get('type')
    symbol = trade_info.get('symbol')
    
    if trade_type == 'open':
        side = trade_info.get('side')
        amount = trade_info.get('amount')
        entry_price = trade_info.get('entry_price')
        position_value = amount * entry_price
        tp_price = trade_info.get('tp_price')
        sl_price = trade_info.get('sl_price')
        balance = trade_info.get('balance')
        
        icon = "📈" if side == 'long' else "📉"
        title = f"{icon} 新規{side.upper()}ポジション"
        
        message = [
            f"**{title}**",
            f"**銘柄:** {symbol}",
            f"**ポジション額:** ${position_value:,.2f} ({amount:.4f} {symbol.split('/')[0]})",
            f"**平均取得価格:** ${entry_price:,.4f}",
            "---",
            f"**利確ポイント:** ${tp_price:,.4f}",
            f"**損切ポイント:** ${sl_price:,.4f}",
            "---",
            f"**現在の口座残高:** ${balance:,.2f}"
        ]
    elif trade_type == 'close':
        pnl = trade_info.get('pnl')
        pnl_percent = trade_info.get('pnl_percent')
        balance = trade_info.get('balance')
        
        icon = "✅" if pnl >= 0 else "❌"
        title = f"{icon} ポジション決済"
        
        message = [
            f"**{title}**",
            f"**銘柄:** {symbol}",
            f"**損益額:** **${pnl:,.2f} ({pnl_percent:+.2f}%)**",
            "---",
            f"**現在の口座残高:** ${balance:,.2f}",
            "**保有ポジション:** なし"
        ]
    else:
        return

    final_message = "\\n".join(message)
    async with aiohttp.ClientSession() as session:
        await send_telegram_message(session, final_message)
        await send_telegram_message(session, final_message)
