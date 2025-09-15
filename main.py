# main.py
import os
import time
import logging
import threading
import schedule
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

import ccxt
import numpy as np

from state_manager import StateManager
from trading_executor import TradingExecutor
from backtester import Backtester

# -----------------------------
# Config & Environment
# -----------------------------
JST = timezone(timedelta(hours=9))
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

BITGET_API_KEY = os.getenv("BITGET_API_KEY_FUTURES")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET_FUTURES")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE_FUTURES")

PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"
MONITORED_COUNT = int(os.getenv("MONITORED_COUNT", "30"))
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "100"))
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "2.0"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.0"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
CYCLE_MINUTES = int(os.getenv("CYCLE_MINUTES", "1"))

STATUS_KEY = os.getenv("STATUS_KEY", "changeme")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BACKTEST_TRADES = int(os.getenv("BACKTEST_TRADES", "1000"))
SLIPPAGE_PCT = float(os.getenv("SLIPPAGE_PCT", "0.005"))
FEE_PCT = float(os.getenv("FEE_PCT", "0.0006"))

# -----------------------------
# Init components
# -----------------------------
state = StateManager()
executor = TradingExecutor(state)
backtester = Backtester(fee_pct=FEE_PCT, slippage_pct=SLIPPAGE_PCT)

# ccxt exchange client for data
exchange = None
try:
    exchange = ccxt.bitget({"enableRateLimit": True})
    exchange.options['defaultType'] = 'swap'
    exchange.load_markets()
    logging.info("Connected to ccxt.bitget for data")
except Exception as e:
    logging.warning("Could not init ccxt for data: %s", e)
    exchange = None

# -----------------------------
# Utility functions
# -----------------------------
def send_telegram_html(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.debug("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        logging.error("Telegram send failed: %s", e)

def fetch_fear_and_greed():
    proxy = os.getenv("PROXY_URL", "https://api.alternative.me/fng/")
    try:
        r = requests.get(proxy, timeout=6).json()
        return r.get("data", [{}])[0]
    except Exception as e:
        logging.debug("F&G fetch failed: %s", e)
        return {"value": "N/A", "value_classification": "Unknown"}

def get_top_symbols_by_volume(limit: int = MONITORED_COUNT) -> List[str]:
    """
    Uses ccxt fetch_tickers / markets to pick top-volume perpetual USDT symbols.
    """
    if not exchange:
        # fallback: common list
        return ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA"][:limit]
    try:
        # fetch tickers and sort by quoteVolume if available
        tickers = exchange.fetch_tickers()
        candidates = []
        for sym, info in tickers.items():
            # filter to USDT perpetual style symbols
            if "USDT" not in sym:
                continue
            # unify symbol like BTC/USDT:USDT -> symbol name BTC
            try:
                base = sym.split("/")[0]
            except Exception:
                continue
            vol = float(info.get("quoteVolume") or info.get("quoteVolume24h") or 0)
            candidates.append((base, vol))
        candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
        symbols = [c[0] for c in candidates][:limit]
        if not symbols:
            return ["BTC","ETH","SOL","BNB"][:limit]
        return symbols
    except Exception as e:
        logging.warning("get_top_symbols_by_volume failed: %s", e)
        return ["BTC","ETH","SOL","BNB"][:limit]

def fetch_ohlcv_ccxt(symbol: str, timeframe: str = "1d", since: int = None, limit: int = 200):
    if not exchange:
        return []
    market_sym = f"{symbol}/USDT:USDT"
    try:
        data = exchange.fetch_ohlcv(market_sym, timeframe=timeframe, since=since, limit=limit)
        # convert to list of dicts
        ohlcv = []
        for row in data:
            ts, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
            ohlcv.append({"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
        return ohlcv
    except Exception as e:
        logging.debug("fetch_ohlcv_ccxt failed for %s: %s", symbol, e)
        return []

def fetch_orderbook_ccxt(symbol: str, limit: int = 50):
    if not exchange:
        return {"bids": [], "asks": [], "bid_vol": 0.0, "ask_vol": 0.0}
    sym = f"{symbol}/USDT:USDT"
    try:
        ob = exchange.fetch_order_book(sym, limit=limit)
        bids = [(float(p), float(q)) for p,q in ob.get("bids", [])]
        asks = [(float(p), float(q)) for p,q in ob.get("asks", [])]
        bid_vol = sum(q for _, q in bids)
        ask_vol = sum(q for _, q in asks)
        return {"bids": bids, "asks": asks, "bid_vol": bid_vol, "ask_vol": ask_vol}
    except Exception as e:
        logging.debug("fetch_orderbook_ccxt failed for %s: %s", symbol, e)
        return {"bids": [], "asks": [], "bid_vol": 0.0, "ask_vol": 0.0}

def calc_atr_from_ohlcv_list(ohlcv: List[Dict[str,Any]], period: int = ATR_PERIOD):
    if not ohlcv or len(ohlcv) < period+1:
        return None
    trs = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i]["high"]
        low = ohlcv[i]["low"]
        prev = ohlcv[i-1]["close"]
        tr = max(high-low, abs(high-prev), abs(low-prev))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    return atr

def generate_ai_comment(symbol: str, price: float, atr: float, ob: Dict[str,Any], fg: Dict[str,Any]) -> str:
    """
    Rule-based layered comment that reads like AI summary.
    """
    parts = []
    # Market psychology
    fg_val = fg.get("value")
    fg_cls = fg.get("value_classification")
    parts.append(f"市場心理: {fg_cls} (Fear&Greed: {fg_val})")

    # ATR
    if atr:
        ratio = atr / price if price else 0
        if ratio > 0.06:
            parts.append(f"ボラティリティ: 高い (ATR={atr:.4f}) — 急激な値動きに注意。")
        elif ratio < 0.02:
            parts.append(f"ボラティリティ: 低め (ATR={atr:.4f}) — レンジ継続の可能性。")
        else:
            parts.append(f"ボラティリティ: 中程度 (ATR={atr:.4f}).")
    else:
        parts.append("ATR: データ不足。")

    # Orderbook
    bid_vol = ob.get("bid_vol", 0.0)
    ask_vol = ob.get("ask_vol", 0.0)
    if bid_vol and ask_vol:
        if bid_vol > ask_vol * 1.5:
            parts.append(f"板: 買いが厚い (buy {bid_vol:.2f} vs sell {ask_vol:.2f}) — 下支え期待。")
        elif ask_vol > bid_vol * 1.5:
            parts.append(f"板: 売りが厚い (sell {ask_vol:.2f} vs buy {bid_vol:.2f}) — 売圧注意。")
        else:
            parts.append(f"板: 拮抗 (buy {bid_vol:.2f} / sell {ask_vol:.2f}).")
    else:
        parts.append("板: データ不足。")

    # Trend via SMA
    ohlcv = fetch_ohlcv_ccxt(symbol, timeframe="1d", limit=30)
    if len(ohlcv) >= 25:
        closes = [x["close"] for x in ohlcv]
        sma7 = sum(closes[-7:]) / 7
        sma25 = sum(closes[-25:]) / 25
        if sma7 > sma25:
            parts.append("短期トレンド: 上向き📈")
        elif sma7 < sma25:
            parts.append("短期トレンド: 下向き📉")
        else:
            parts.append("短期トレンド: 横ばい。")
    else:
        parts.append("チャート: データ不足。")

    # Score aggregation
    score = 50.0
    # ATR contribution
    if atr:
        if ratio > 0.06: score -= 5
        elif ratio < 0.02: score += 3
    # orderbook contribution
    if bid_vol and ask_vol:
        if bid_vol > ask_vol * 1.5: score += 5
        elif ask_vol > bid_vol * 1.5: score -= 5
    # Fear greed
    try:
        fgv = int(fg_val) if fg_val and str(fg_val).isdigit() else 50
        if fgv > 70:
            score -= 5
        elif fgv < 30:
            score += 3
    except Exception:
        pass

    parts.append(f"総合スコア (0-100): {min(max(round(score,1),0),100)}")

    return "\n".join(parts), score

# -----------------------------
# Signal & Execution
# -----------------------------
def evaluate_and_maybe_trade(symbol: str, price: float, atr: float, ob: Dict[str,Any], fg: Dict[str,Any]):
    """
    Decide whether to open positions based on rule, backtest filter, and execute using executor (paper or real).
    """
    # simple price momentum rule: 1d change
    ohlcv_2 = fetch_ohlcv_ccxt(symbol, timeframe="1d", limit=2)
    if len(ohlcv_2) < 2:
        logging.debug("skip %s: not enough 1d data", symbol)
        return None

    today_close = ohlcv_2[-1]["close"]
    prev_close = ohlcv_2[-2]["close"]
    change_pct = (today_close / prev_close - 1.0) * 100.0
    threshold = float(os.getenv("PRICE_CHANGE_THRESHOLD_PCT", "5.0"))

    # build candidate trade dict
    candidate = None
    if change_pct >= threshold:
        # candidate long
        tp = today_close + TP_ATR_MULT * (atr or 0)
        sl = today_close - SL_ATR_MULT * (atr or 0)
        candidate = {"symbol": symbol, "side": "long", "entry_price": price, "tp": tp, "sl": sl, "signal_strength": change_pct}
    elif change_pct <= -threshold:
        tp = today_close - TP_ATR_MULT * (atr or 0)
        sl = today_close + SL_ATR_MULT * (atr or 0)
        candidate = {"symbol": symbol, "side": "short", "entry_price": price, "tp": tp, "sl": sl, "signal_strength": change_pct}

    if not candidate:
        return None

    # run backtest filter: fetch historical ohlcv for this symbol and run backtester with same rule
    hist = fetch_ohlcv_ccxt(symbol, timeframe="1d", limit=1200)  # fetch enough history
    if not hist or len(hist) < 50:
        logging.debug("backtest skip for %s: insufficient history", symbol)
        # allow trade if ATR and ob ok? For safety, skip trade if no history
        return None

    rule = {
        "price_change_threshold_pct": abs(candidate["signal_strength"]),
        "atr_period": ATR_PERIOD,
        "tp_atr_mult": TP_ATR_MULT,
        "sl_atr_mult": SL_ATR_MULT
    }
    bt_result = backtester.run_rule_backtest(hist, rule, max_trades=BACKTEST_TRADES)
    # Filter: simple threshold rule for pf and winrate
    pf = bt_result.get("profit_factor") or 0
    wr = bt_result.get("win_rate") or 0
    sharpe = bt_result.get("sharpe") or 0
    # Heuristics: require PF>1 and winrate>40 or sharpe>0.5
    allow = False
    if (pf is None):
        allow = False
    else:
        if (pf >= 1.0 and wr >= 40) or (sharpe and sharpe > 0.5):
            allow = True

    # Compose AI comment and score
    ai_comment, score = generate_ai_comment(symbol, price, atr, ob, fg)

    # If allowed -> execute simulated order sizing
    if allow:
        size_usd = POSITION_SIZE_USD
        # dynamic adjustment: if backtest suggests higher PF, can increase size by factor (capped)
        if pf and pf > 1.5:
            size_usd *= min(1.5, 1 + (pf - 1))
        # check balance
        balance = state.get_balance()
        # simple risk cap: don't allocate more than 10% of balance to one position
        size_usd = min(size_usd, balance * 0.1)

        # Enter position (paper or live)
        rec = executor.open_position(symbol, candidate["side"], size_usd,
                                     entry_price=price, take_profit=candidate["tp"], stop_loss=candidate["sl"],
                                     leverage=3.0, partial_steps=[0.5,0.25,0.25])
        # Notify
        msg = (
            f"<b>📥 New Position</b>\n"
            f"<b>{symbol}</b> {candidate['side'].upper()} (Sim:{PAPER_TRADING})\n"
            f"Entry: <code>{price:.6f}</code>\n"
            f"Size(USD): <code>{size_usd:.2f}</code>\n"
            f"TP: <code>{candidate['tp']:.6f}</code>  SL: <code>{candidate['sl']:.6f}</code>\n"
            f"Backtest PF: <code>{pf:.3f}</code> WinRate: <code>{wr:.2f}%</code> Sharpe: <code>{sharpe}</code>\n"
            f"<pre>{ai_comment}</pre>\n"
        )
        send_telegram_html(msg)
        logging.info("Opened candidate %s %s", symbol, candidate['side'])
        # return details
        return {"executed": True, "symbol": symbol, "pf": pf, "win_rate": wr, "sharpe": sharpe}
    else:
        logging.debug("Candidate filtered out by backtest: %s pf=%s wr=%s", symbol, pf, wr)
        return {"executed": False, "pf": pf, "win_rate": wr}

# -----------------------------
# Cycle logic
# -----------------------------
def run_cycle():
    logging.info("=== cycle start === %s", datetime.now(JST).isoformat())
    symbols = get_top_symbols_by_volume(MONITORED_COUNT)
    logging.info("Monitoring %d symbols", len(symbols))
    fg = fetch_fear_and_greed()
    snapshot = {"timestamp": datetime.now(JST).isoformat(), "symbols": {}}

    for sym in symbols:
        try:
            price = None
            try:
                ticker = exchange.fetch_ticker(f"{sym}/USDT:USDT")
                price = float(ticker.get("last") or ticker.get("close") or 0)
            except Exception:
                # fallback to ohlcv last close
                hist = fetch_ohlcv_ccxt(sym, timeframe="1m", limit=3)
                if hist:
                    price = float(hist[-1]["close"])
            if not price or price == 0:
                logging.debug("skip %s: price not found", sym)
                continue

            ohlcv_daily = fetch_ohlcv_ccxt(sym, timeframe="1d", limit=ATR_PERIOD+5)
            atr = calc_atr_from_ohlcv_list(ohlcv_daily, period=ATR_PERIOD) if ohlcv_daily else None
            ob = fetch_orderbook_ccxt(sym, limit=50)
            ai_comment, score = generate_ai_comment(sym, price, atr, ob, fg)

            snapshot["symbols"][sym] = {
                "price": price,
                "atr": atr,
                "orderbook": {"bid_vol": ob.get("bid_vol"), "ask_vol": ob.get("ask_vol")},
                "score": score,
                "ai_comment": ai_comment
            }

            # Evaluate candidate & possibly trade
            evaluate_and_maybe_trade(sym, price, atr, ob, fg)

        except Exception as e:
            logging.exception("Error processing %s: %s", sym, e)
        time.sleep(0.15)  # gentle pacing

    # update last snapshot for status
    state.update_last_snapshot(snapshot)
    logging.info("=== cycle finished === %s", datetime.now(JST).isoformat())

# -----------------------------
# Periodic reports and position checks
# -----------------------------
def check_positions_and_manage():
    # examine each open position for TP/SL reached (price based)
    positions = state.get_positions()
    fg = fetch_fear_and_greed()
    for sym, pos in list(positions.items()):
        try:
            price = None
            try:
                ticker = exchange.fetch_ticker(f"{sym}/USDT:USDT")
                price = float(ticker.get("last") or ticker.get("close") or 0)
            except Exception:
                continue
            side = pos["side"]
            tp = float(pos["take_profit"])
            sl = float(pos["stop_loss"])
            # multi-step partial close logic example:
            # if TP reached do partial close according to stored plan (for simplicity, close all)
            if side == "long":
                if price >= tp:
                    rec = state.close_position(sym, price, reason="TP")
                    send_telegram_html(f"<b>✅ TP reached</b>\n<b>{sym}</b>\nEntry:{rec['entry_price']:.6f}\nExit:{rec['exit_price']:.6f}\nPnL:{rec['pnl']:.6f}\n")
                elif price <= sl:
                    rec = state.close_position(sym, price, reason="SL")
                    send_telegram_html(f"<b>❌ SL triggered</b>\n<b>{sym}</b>\nEntry:{rec['entry_price']:.6f}\nExit:{rec['exit_price']:.6f}\nPnL:{rec['pnl']:.6f}\n")
            else:
                if price <= tp:
                    rec = state.close_position(sym, price, reason="TP")
                    send_telegram_html(f"<b>✅ TP reached (SHORT)</b>\n<b>{sym}</b>\nPnL:{rec['pnl']:.6f}\n")
                elif price >= sl:
                    rec = state.close_position(sym, price, reason="SL")
                    send_telegram_html(f"<b>❌ SL triggered (SHORT)</b>\n<b>{sym}</b>\nPnL:{rec['pnl']:.6f}\n")
        except Exception as e:
            logging.exception("check positions failed for %s: %s", sym, e)

def hourly_report():
    # build human-friendly status
    bal = state.get_balance()
    stats = state.get_stats()
    positions = state.get_positions()
    fg = fetch_fear_and_greed()
    msg = (
        f"<b>🕒 Hourly Report ({datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')})</b>\n"
        f"<b>Balance:</b> <code>{bal:.2f} USDT</code>\n"
        f"<b>WinRate:</b> <code>{stats.get('win_rate', 0.0):.2f}%</code>\n"
        f"<b>Positions:</b> <code>{len(positions)}</code>\n\n"
    )
    if positions:
        for sym, p in positions.items():
            msg += (f"<b>{sym}</b> {p['side'].upper()} Entry:<code>{p['entry_price']:.6f}</code> "
                    f"TP:<code>{p['take_profit']:.6f}</code> SL:<code>{p['stop_loss']:.6f}</code>\n")
    else:
        msg += "No open positions.\n"
    msg += f"\nFear&Greed: {fg.get('value')} ({fg.get('value_classification')})"
    send_telegram_html(msg)

# -----------------------------
# Scheduler
# -----------------------------
def scheduler_loop():
    schedule.every(CYCLE_MINUTES).minutes.do(run_cycle)
    schedule.every(CYCLE_MINUTES).minutes.do(check_positions_and_manage)
    # hourly report at JST top-of-hour
    while True:
        schedule.run_pending()
        # fire hourly at top of JST hour
        now = datetime.now(timezone.utc).astimezone(JST)
        if now.minute == 0 and now.second < 5:
            try:
                hourly_report()
                time.sleep(61)
            except Exception as e:
                logging.exception("hourly_report error: %s", e)
        time.sleep(1)

# -----------------------------
# Flask status endpoint
# -----------------------------
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route("/")
def hello():
    return "Trend Sentinel (Bitget Futures) - monitoring"

@app.route("/status")
def status():
    key = request.args.get("key", "")
    if key != STATUS_KEY:
        return jsonify({"error": "unauthorized"}), 401
    snap = state.get_state_snapshot()
    snap["server_time_jst"] = datetime.now(JST).isoformat()
    snap["paper_trading"] = PAPER_TRADING
    return jsonify(snap)

# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    logging.info("Starting Trend Sentinel (Bitget Futures). PAPER_TRADING=%s", PAPER_TRADING)
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    # run initial cycle immediately
    try:
        run_cycle()
    except Exception as e:
        logging.exception("initial run failed: %s", e)
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
