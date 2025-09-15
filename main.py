# main.py
import os
import time
import logging
import schedule
import threading
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from state_manager import StateManager
from trading_executor import TradingExecutor

# ---------------------------
# Config (env)
# ---------------------------
JST = timezone(timedelta(hours=9))
MONITORED_SYMBOLS = os.getenv("MONITORED_SYMBOLS", "BTC,ETH,SOL,BNB").split(",")
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "100"))
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "1.0"))   # base multiplier (we use 1x,2x,3x steps)
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.0"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
PRICE_CHANGE_THRESHOLD_PCT = float(os.getenv("PRICE_CHANGE_THRESHOLD_PCT", "5.0"))
PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"

BITGET_API_KEY = os.getenv("BITGET_API_KEY")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATUS_KEY = os.getenv("STATUS_KEY", "changeme")

# Basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# State / Executor
state = StateManager()
executor = TradingExecutor(BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE, paper=PAPER_TRADING)

# ---------------------------
# Utilities: Bitget public data via REST
# (simple fetchers; used for price/ohlcv/orderbook)
# ---------------------------
BITGET_BASE = os.getenv("BITGET_BASE", "https://api.bitget.com")

def _get(path: str, params: dict=None, timeout=8):
    url = f"{BITGET_BASE}{path}"
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.debug("GET failed %s %s", url, e)
        return {}

def fetch_price(symbol: str) -> Optional[float]:
    """Attempt to fetch last price for symbol (e.g. BTC) via Bitget public ticker"""
    try:
        # try futures ticker first (mix/v1)
        symbol_upper = symbol.upper()
        # try multiple endpoints for robustness
        for path, params in [
            ("/api/mix/v1/market/ticker", {"symbol": f"{symbol_upper}USDT_UMCBL"}),  # some bitget pairs
            ("/api/spot/v1/market/ticker", {"symbol": f"{symbol_upper}USDT"}),
            ("/api/mix/v1/market/ticker", {"symbol": f"{symbol_upper}USDT"}), # fallback
        ]:
            data = _get(path, params=params)
            if data and "data" in data:
                d = data.get("data")
                if isinstance(d, dict) and "last" in d:
                    return float(d["last"])
                if isinstance(d, list) and len(d) > 0 and "last" in d[0]:
                    return float(d[0]["last"])
        return None
    except Exception as e:
        logging.debug("fetch_price error %s", e)
        return None

def fetch_ohlcv(symbol: str, granularity: int = 86400, limit: int = 100):
    """
    Fetch candles (attempt spot candles endpoint). Returns list oldest->newest of dicts with close etc.
    """
    try:
        data = _get("/api/spot/v1/market/candles", params={"symbol": f"{symbol.upper()}USDT", "granularity": granularity, "limit": limit})
        arr = data.get("data", []) or []
        parsed = []
        for item in arr:
            # item can be list [ts,open,high,low,close,volume]
            try:
                if isinstance(item, list) and len(item) >= 6:
                    ts = int(item[0])
                    if ts > 1e12:
                        ts = ts // 1000
                    parsed.append({"time": datetime.fromtimestamp(ts, JST), "open": float(item[1]), "high": float(item[2]), "low": float(item[3]), "close": float(item[4]), "volume": float(item[5])})
                elif isinstance(item, dict):
                    ts = int(item.get("timestamp") or item.get("time") or item.get("id"))
                    if ts > 1e12: ts = ts // 1000
                    parsed.append({"time": datetime.fromtimestamp(ts, JST), "open": float(item.get("open")), "high": float(item.get("high")), "low": float(item.get("low")), "close": float(item.get("close")), "volume": float(item.get("volume", 0))})
            except Exception:
                continue
        return list(reversed(parsed))
    except Exception:
        return []

def calc_atr(symbol: str, period: int = ATR_PERIOD) -> Optional[float]:
    ohlcv = fetch_ohlcv(symbol, granularity=86400, limit=period+2)
    if not ohlcv or len(ohlcv) < period+1:
        return None
    trs = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i]["high"]
        low = ohlcv[i]["low"]
        prev = ohlcv[i-1]["close"]
        tr = max(high - low, abs(high - prev), abs(low - prev))
        trs.append(tr)
    if not trs:
        return None
    atr = sum(trs[-period:]) / period
    return float(atr)

def compute_tp_levels(entry_price: float, atr: float, side: str):
    """
    Return list of tp levels as dicts with pct to close:
      - first: 50%
      - second: 25%
      - third: 25% (remaining)
    Prices: TP multipliers 1x, 2x, 3x of TP_ATR_MULT (so actual: entry +/- k*TP_ATR_MULT*atr)
    """
    mult = TP_ATR_MULT
    levels = []
    if side.lower() == "long":
        levels.append({"price": entry_price + mult * atr, "pct": 0.5, "closed": False, "label": "TP1 (50%)"})
        levels.append({"price": entry_price + (2 * mult) * atr, "pct": 0.25, "closed": False, "label": "TP2 (25%)"})
        levels.append({"price": entry_price + (3 * mult) * atr, "pct": 0.25, "closed": False, "label": "TP3 (残り)"})
    else:
        levels.append({"price": entry_price - mult * atr, "pct": 0.5, "closed": False, "label": "TP1 (50%)"})
        levels.append({"price": entry_price - (2 * mult) * atr, "pct": 0.25, "closed": False, "label": "TP2 (25%)"})
        levels.append({"price": entry_price - (3 * mult) * atr, "pct": 0.25, "closed": False, "label": "TP3 (残り)"})
    return levels

# ---------------------------
# Simple news / AI-like comment generator (rules-based)
# ---------------------------
def fetch_fear_and_greed():
    try:
        j = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        return j.get("data", [{}])[0]
    except Exception:
        return {"value": "N/A", "value_classification": "Unknown"}

def generate_ai_comment(symbol: str, price: float):
    fg = fetch_fear_and_greed()
    fgv = fg.get("value", "N/A")
    atr = calc_atr(symbol) or 0.0
    ratio = (atr / price) if price and atr else 0.0
    vol_comment = "高ボラ" if ratio > 0.05 else ("低ボラ" if ratio < 0.02 else "中ボラ")
    return f"市場状態: FG={fgv} / ボラ: {vol_comment} / ATR={atr:.4f}"

# ---------------------------
# Telegram helper
# ---------------------------
def send_telegram_html(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.debug("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.exception("Telegram send error: %s", e)

# ---------------------------
# Signal rules (simple momentum based)
# ---------------------------
def compute_1d_change_pct(symbol: str) -> Optional[float]:
    ohlcv = fetch_ohlcv(symbol, granularity=86400, limit=2)
    if not ohlcv or len(ohlcv) < 2:
        return None
    return (ohlcv[-1]["close"] / ohlcv[-2]["close"] - 1.0) * 100.0

# ---------------------------
# Main trading cycle
# ---------------------------
def run_trading_cycle():
    logging.info("=== Trading cycle start ===")
    fg = fetch_fear_and_greed()
    for s in MONITORED_SYMBOLS:
        sym = s.strip().upper()
        try:
            price = fetch_price(sym)
            if price is None:
                logging.debug("no price for %s", sym)
                continue

            # check existing position
            if state.has_position(sym):
                pos = state.get_position(sym)
                if not pos:
                    continue
                side = pos["side"]
                # check TP levels (iterate in order)
                for lev in pos["tp_levels"]:
                    if lev.get("closed"):
                        continue
                    tp_price = float(lev["price"])
                    pct = float(lev["pct"])
                    label = lev.get("label", "")
                    # condition depends on long/short
                    hit = (side == "long" and price >= tp_price) or (side == "short" and price <= tp_price)
                    if hit:
                        # compute amount to close
                        initial_amount = float(pos["initial_amount"])
                        close_amount = initial_amount * pct
                        # ensure not exceeding remaining
                        remaining = float(pos["amount"])
                        close_amount = min(close_amount, remaining)
                        # execute close (paper or real)
                        if not PAPER_TRADING:
                            res = executor.close_futures_position(sym, side, close_amount)
                            logging.info("Close order result: %s", res)
                        # update state
                        rec = state.reduce_position(sym, close_amount, price, reason=f"TP:{label}")
                        lev["closed"] = True
                        # after partial close, move remaining SL up to breakeven or ATR-based improved SL
                        atr = calc_atr(sym) or 0.0
                        try:
                            # new SL: for long move to entry or entry + 0.5*atr (safer)
                            with_update = False
                            if pos and pos.get("amount", 0) > 0:
                                if side == "long":
                                    new_sl = max(pos["entry_price"], pos["entry_price"] + 0.5 * (atr if atr else 0.0))
                                else:
                                    new_sl = min(pos["entry_price"], pos["entry_price"] - 0.5 * (atr if atr else 0.0))
                                # update in state
                                # direct mutation is okay with state internal locking since get_position returns a ref
                                pos["stop_loss"] = float(new_sl)
                                with_update = True
                                state.save_state()
                        except Exception:
                            pass

                        # notify
                        ai = generate_ai_comment(sym, price)
                        txt = (
                            f"<b>📤 部分利確 ({label})</b>\n"
                            f"<b>{sym}</b> ({side.upper()})\n"
                            f"Close amount: <code>{close_amount:.6f}</code>\n"
                            f"Price: <code>{price:.6f}</code>\n"
                            f"残量: <code>{pos.get('amount'):.6f}</code>\n"
                            f"\n{ai}"
                        )
                        send_telegram_html(txt)
                        # move to next tp (we break loop to avoid double processing in same cycle)
                        break

                # after TP checks, check SL (for remaining)
                # re-fetch position in case it was removed
                if not state.has_position(sym):
                    continue
                pos = state.get_position(sym)
                if not pos:
                    continue
                sl = float(pos["stop_loss"])
                side = pos["side"]
                # SL hit condition
                sl_hit = (side == "long" and price <= sl) or (side == "short" and price >= sl)
                if sl_hit:
                    remaining_amount = float(pos["amount"])
                    if not PAPER_TRADING:
                        res = executor.close_futures_position(sym, side, remaining_amount)
                        logging.info("Close order result (SL): %s", res)
                    rec = state.close_position(sym, price, reason="SL")
                    ai = generate_ai_comment(sym, price)
                    txt = (
                        f"<b>❌ 損切 (SL)</b>\n"
                        f"<b>{sym}</b> ({side.upper()})\n"
                        f"Exit price: <code>{price:.6f}</code>\n"
                        f"PnL: <code>{rec['pnl']:.6f} USDT</code>\n"
                        f"Reason: SL\n\n{ai}"
                    )
                    send_telegram_html(txt)
                # end position handling

            else:
                # no position -> simple entry rule
                change_1d = compute_1d_change_pct(sym)
                if change_1d is None:
                    continue
                if change_1d >= PRICE_CHANGE_THRESHOLD_PCT:
                    # open long (futures)
                    atr = calc_atr(sym)
                    if not atr:
                        continue
                    entry_price = price
                    tp_levels = compute_tp_levels(entry_price, atr, "long")
                    stop_loss = entry_price - SL_ATR_MULT * atr
                    amount = POSITION_SIZE_USD / entry_price
                    # place order
                    if not PAPER_TRADING:
                        res = executor.open_futures_position(sym, "long", amount)
                    # write to state (simulate or after order)
                    state.open_position(sym, "long", entry_price, amount, tp_levels, stop_loss)
                    ai = generate_ai_comment(sym, price)
                    txt = (
                        f"<b>📥 新規建玉 (LONG)</b>\n"
                        f"<b>{sym}</b>\nEntry: <code>{entry_price:.6f}</code>\n"
                        f"Size: <code>{amount:.6f}</code>\nTP: <code>{tp_levels[0]['price']:.6f}</code> / {tp_levels[1]['price']:.6f} / {tp_levels[2]['price']:.6f}\n"
                        f"SL: <code>{stop_loss:.6f}</code>\n\n{ai}"
                    )
                    send_telegram_html(txt)

                elif change_1d <= -PRICE_CHANGE_THRESHOLD_PCT:
                    # open short
                    atr = calc_atr(sym)
                    if not atr:
                        continue
                    entry_price = price
                    tp_levels = compute_tp_levels(entry_price, atr, "short")
                    stop_loss = entry_price + SL_ATR_MULT * atr
                    amount = POSITION_SIZE_USD / entry_price
                    if not PAPER_TRADING:
                        res = executor.open_futures_position(sym, "short", amount)
                    state.open_position(sym, "short", entry_price, amount, tp_levels, stop_loss)
                    ai = generate_ai_comment(sym, price)
                    txt = (
                        f"<b>📥 新規建玉 (SHORT)</b>\n"
                        f"<b>{sym}</b>\nEntry: <code>{entry_price:.6f}</code>\n"
                        f"Size: <code>{amount:.6f}</code>\nTP: <code>{tp_levels[0]['price']:.6f}</code> / {tp_levels[1]['price']:.6f} / {tp_levels[2]['price']:.6f}\n"
                        f"SL: <code>{stop_loss:.6f}</code>\n\n{ai}"
                    )
                    send_telegram_html(txt)
            # light sleep to avoid too many API calls
            time.sleep(0.15)
        except Exception as e:
            logging.exception("Error in run_trading_cycle for %s: %s", sym, e)

    # update snapshot
    state.update_last_snapshot({"ts": datetime.now(JST).isoformat()})
    logging.info("=== Trading cycle finished ===")

# ---------------------------
# Scheduler
# ---------------------------
def scheduler_loop():
    # run trading cycle every minute (as example); user can change
    schedule.every(1).minutes.do(run_trading_cycle)
    while True:
        schedule.run_pending()
        time.sleep(1)

# ---------------------------
# HTTP status endpoint (protected)
# ---------------------------
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route("/status")
def status():
    key = request.args.get("key", "")
    if key != STATUS_KEY:
        return jsonify({"error": "unauthorized"}), 401
    snap = state.get_state_snapshot()
    snap["server_time_jst"] = datetime.now(JST).isoformat()
    return jsonify(snap)

# ---------------------------
# Entrypoint
# ---------------------------
if __name__ == "__main__":
    logging.info("Starting bot (paper=%s). Monitored: %s", PAPER_TRADING, MONITORED_SYMBOLS)
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
