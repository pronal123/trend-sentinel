# main.py
import os
import time
import logging
import schedule
import asyncio
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify
from threading import Thread

from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor  # assumes file exists in repo

# -------------------------
# env / logger
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
JST = timezone(timedelta(hours=9))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # numeric or @channel

app = Flask(__name__)

# -------------------------
# core instances
# -------------------------
state_manager = StateManager()
data_aggregator = DataAggregator(state_manager)
trading_executor = TradingExecutor(state_manager)  # uses state_manager in constructor

# Watchlist base (BTC/ETH always)
BASE_WATCH = ["BTC", "ETH"]

# -------------------------
# Helpers
# -------------------------
def build_watchlist():
    watch = set([s.upper() for s in BASE_WATCH])

    # add held positions
    positions = state_manager.get_all_active_positions()
    for sym in positions.keys():
        watch.add(sym.upper())

    # add coingecko trending
    try:
        trending = data_aggregator.get_coingecko_trending_symbols(top_n=5)
        for t in trending:
            watch.add(t.upper())
    except Exception as e:
        logging.warning(f"Failed to fetch trending: {e}")

    return sorted(list(watch))

def send_telegram_message(text: str, parse_mode="HTML"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.info("Telegram not configured. Skipping send.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Telegram send failed: {r.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"Telegram send exception: {e}")
        return False

def format_status_payload(symbols, snapshots, ai_comments, chains_perf):
    positions = state_manager.get_all_active_positions()
    balance = trading_executor.get_account_balance_usd()
    win_rate = state_manager.get_win_rate()

    summary = {
        "long_signals": 0, "short_signals": 0, "spike_alerts": 0
    }  # placeholder; can be filled by analysis engine

    payload = {
        "timestamp_jst": datetime.now(JST).isoformat(),
        "win_rate": win_rate,
        "balance": balance,
        "positions": positions,
        "watchlist": symbols,
        "snapshots": snapshots,
        "ai_comments": ai_comments,
        "summary": summary,
        "chains": chains_perf
    }
    return payload

# -------------------------
# Core cycle: build status and optionally notify Telegram
# -------------------------
import requests  # used in telegram helper and elsewhere

def build_status_and_notify(send_telegram=False, is_daily_summary=False):
    symbols = build_watchlist()
    logging.info(f"Building status for watchlist: {symbols}")

    snapshots = {}
    ai_comments = {}

    # 1) get chain perf for daily/regular sections (8 chains fixed)
    chain_list = ["ethereum", "solana", "base", "bnb", "arbitrum", "optimism", "polygon", "avalanche"]
    chains_perf = data_aggregator.get_chain_performance(chain_list)

    # 2) for each symbol: snapshot + AI proposal (every time, as requested)
    for sym in symbols:
        try:
            snap = data_aggregator.build_market_snapshot(sym)
            snapshots[sym] = snap
            # check if held
            pos = state_manager.get_all_active_positions().get(sym)
            ai_text = data_aggregator.get_ai_trade_proposal(sym, snap, position=pos, priority=bool(pos))
            ai_comments[sym] = ai_text
        except Exception as e:
            logging.error(f"Error handling {sym}: {e}")
            snapshots[sym] = {}
            ai_comments[sym] = f"{sym}: エラーが発生しました"

    payload = format_status_payload(symbols, snapshots, ai_comments, chains_perf)

    # Optionally send Telegram message
    if send_telegram:
        # build pretty message: prioritize held positions
        lines = []
        now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M JST")
        title = f"📡 トレンドセンチネル速報（{now_str}）"
        lines.append(title)
        lines.append("")

        positions = state_manager.get_all_active_positions()
        if positions:
            lines.append("【保有中の銘柄】")
            for s, pos in positions.items():
                # AI comment summary (first 3 lines)
                comment = ai_comments.get(s, "")
                snippet = "\n".join(comment.splitlines()[:4])
                lines.append(f"・{s} ({pos.get('side', 'N/A')})\n{snippet}\n")
        # New candidates
        lines.append("【新規候補】")
        for s, comment in ai_comments.items():
            if s not in positions:
                snippet = "\n".join(comment.splitlines()[:2])
                lines.append(f"・{s}\n{snippet}\n")

        # Chains performance
        lines.append("🌍 チェーン別24hパフォーマンス")
        for chain, perf in chains_perf.items():
            lines.append(f"・{chain.capitalize()}: {perf:+.2f}%")

        # Basic stats
        lines.append("")
        lines.append(f"💰 残高: {payload['balance']:.2f} USDT")
        lines.append(f"📊 勝率: {payload['win_rate']:.2f}%")

        # daily summary addition
        if is_daily_summary:
            # add top gainers/losers (simple derivation)
            try:
                df_list = []
                for s, snap in snapshots.items():
                    p24 = snap.get("price_change_24h")
                    if p24 is not None:
                        df_list.append((s, float(p24)))
                if df_list:
                    df_list.sort(key=lambda x: x[1], reverse=True)
                    lines.append("\n📈 上昇TOP3")
                    for t in df_list[:3]:
                        lines.append(f"・{t[0]} {t[1]:+.2f}%")
                    lines.append("\n📉 下落TOP3")
                    for t in df_list[-3:]:
                        lines.append(f"・{t[0]} {t[1]:+.2f}%")
            except Exception:
                pass

        final_msg = "\n".join(lines)
        # Send (HTML mode not heavily used here; messages are plain / simple)
        send_telegram_message(final_msg, parse_mode="HTML")

    return payload

# -------------------------
# Scheduler: JST times -> converted to UTC schedule entries
# -------------------------
def run_cycle_and_notify_wrapper():
    try:
        # If you have async trading cycle, call here. For now, use synchronous status builder
        payload = build_status_and_notify(send_telegram=True, is_daily_summary=False)
        logging.info("Cycle done & notification sent.")
    except Exception as e:
        logging.error(f"run_cycle_and_notify_wrapper failed: {e}")

def send_daily_summary_wrapper():
    try:
        payload = build_status_and_notify(send_telegram=True, is_daily_summary=True)
        logging.info("Daily summary sent.")
    except Exception as e:
        logging.error(f"send_daily_summary_wrapper failed: {e}")

# Setup schedule using UTC times corresponding to JST 02/08/14/20 and daily 21:00 JST
# JST to UTC: subtract 9 hours
schedule.every().day.at("17:00").do(run_cycle_and_notify_wrapper)  # JST 02:00
schedule.every().day.at("23:00").do(run_cycle_and_notify_wrapper)  # JST 08:00
schedule.every().day.at("05:00").do(run_cycle_and_notify_wrapper)  # JST 14:00
schedule.every().day.at("11:00").do(run_cycle_and_notify_wrapper)  # JST 20:00
# daily summary at JST 21:00 => UTC 12:00
schedule.every().day.at("12:00").do(send_daily_summary_wrapper)   # JST 21:00

def scheduler_thread():
    logging.info("Scheduler thread started.")
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except Exception as e:
            logging.error(f"Scheduler error: {e}")
            time.sleep(10)

# -------------------------
# Flask endpoints
# -------------------------
@app.route("/")
def health():
    return "OK - Trend Sentinel Bot is running"

@app.route("/status")
def status():
    payload = build_status_and_notify(send_telegram=False, is_daily_summary=False)
    return jsonify(payload)

# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    logging.info("Starting Trend Sentinel service...")
    # start scheduler thread
    t = Thread(target=scheduler_thread, daemon=True)
    t.start()

    # run immediate initial build (non-blocking)
    try:
        build_status_and_notify(send_telegram=False)
    except Exception as e:
        logging.error(f"Initial run failed: {e}")

    port = int(os.environ.get("PORT", 5000))
    # Flask runs in main thread
    app.run(host="0.0.0.0", port=port)
