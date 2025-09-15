# telegram_notifier.py
import os
import logging
import requests
from datetime import datetime, timezone, timedelta
from state_manager import StateManager

# 環境変数から取得
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

state = StateManager()

JST = timezone(timedelta(hours=9))


def send_telegram_message(message: str):
    """Telegramへメッセージ送信"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram設定が未設定です。通知できません。")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"Telegram通知失敗: {response.text}")
    except Exception as e:
        logging.error(f"Telegram送信エラー: {e}")


def notify_entry(token: str, side: str, size: float, price: float, balance: dict):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    snapshot = state.get_last_snapshot()
    market_info = ""
    if snapshot:
        market_info = f"\n📊 市況: {snapshot.get('price', '?')} USDT, ATR={snapshot.get('atr', '?')}, Score={snapshot.get('score', '?')}"

    msg = (
        f"🟢 *新規エントリー*\n"
        f"━━━━━━━━━━━━━━\n"
        f"日時: {now}\n"
        f"銘柄: {token}\n"
        f"方向: {side}\n"
        f"数量: {size}\n"
        f"価格: {price}\n"
        f"残高: {balance.get('USDT', '?'):.2f} USDT\n"
        f"{market_info}"
    )
    send_telegram_message(msg)


def notify_exit(token: str, side: str, size: float, price: float, pnl: float, reason: str, balance: dict):
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    snapshot = state.get_last_snapshot()
    market_info = ""
    if snapshot:
        market_info = f"\n📊 市況: {snapshot.get('price', '?')} USDT, ATR={snapshot.get('atr', '?')}, Score={snapshot.get('score', '?')}"

    msg = (
        f"🔴 *ポジションクローズ*\n"
        f"━━━━━━━━━━━━━━\n"
        f"日時: {now}\n"
        f"銘柄: {token}\n"
        f"方向: {side}\n"
        f"数量: {size}\n"
        f"価格: {price}\n"
        f"損益: {pnl:.2f} USDT\n"
        f"理由: {reason}\n"
        f"残高: {balance.get('USDT', '?'):.2f} USDT\n"
        f"{market_info}"
    )
    send_telegram_message(msg)


def notify_hourly(balance: dict):
    """毎時ちょうどに残高とポジション一覧を通知"""
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    positions = state.get_all_positions()
    today = datetime.now(JST).strftime("%Y-%m-%d")
    pnl_today = state.get_daily_pnl(today)

    # ポジション整形
    if positions:
        pos_text = "\n".join(
            [f"- {t}: {d.get('side')} {d.get('size')} @ {d.get('entry_price')}" for t, d in positions.items()]
        )
    else:
        pos_text = "なし"

    snapshot = state.get_last_snapshot()
    market_info = ""
    if snapshot:
        market_info = (
            f"\n📊 市況スナップショット\n"
            f"価格: {snapshot.get('price', '?')} USDT\n"
            f"ATR: {snapshot.get('atr', '?')}\n"
            f"Score: {snapshot.get('score', '?')}"
        )

    msg = (
        f"⏰ *定時レポート*\n"
        f"━━━━━━━━━━━━━━\n"
        f"日時: {now}\n"
        f"残高: {balance.get('USDT', '?'):.2f} USDT\n"
        f"本日確定損益: {pnl_today['realized_usdt']:.2f} USDT / {pnl_today['realized_jpy']:.0f} 円\n"
        f"エントリー回数: {pnl_today['entry_count']} 回\n"
        f"決済回数: {pnl_today['exit_count']} 回\n"
        f"保有ポジション:\n{pos_text}"
        f"{market_info}"
    )
    send_telegram_message(msg)
