import os
import time
import json
import logging
import requests
import schedule
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from state_manager import StateManager
from trading_executor import TradingExecutor

# ---- Config ----
JST = timezone(timedelta(hours=9))
MONITORED_SYMBOLS = [s.strip().upper() for s in os.getenv("MONITORED_SYMBOLS", "BTC,ETH,SOL,BNB,ARB,OP,MATIC,AVAX").split(",")]
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "100.0"))
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "2.0"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.0"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
PRICE_CHANGE_THRESHOLD_PCT = float(os.getenv("PRICE_CHANGE_THRESHOLD_PCT", "5.0"))
PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"
STATUS_KEY = os.getenv("STATUS_KEY", "changeme")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BITGET_BASE = os.getenv("BITGET_BASE", "https://api.bitget.com")

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Components
state = StateManager()
executor = TradingExecutor()

# ---- Utility: Bitget public endpoints (simple, robust) ----
def bitget_get_json(path: str, params: dict=None, timeout=8):
    url = f"{BITGET_BASE}{path}"
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.debug("bitget_get_json FAIL %s %s", url, e)
        return {}

def fetch_price(symbol: str) -> Optional[float]:
    """
    Use Bitget market ticker for current last price.
    symbol like "BTC" => query symbol=BTCUSDT
    """
    try:
        path = "/api/spot/v1/market/ticker"
        data = bitget_get_json(path, params={"symbol": f"{symbol}USDT"})
        d = data.get("data")
        if not d:
            return None
        if isinstance(d, list) and d:
            last = d[0].get("last") or d[0].get("close")
        elif isinstance(d, dict):
            last = d.get("last") or d.get("close")
        else:
            last = None
        return float(last) if last is not None else None
    except Exception as e:
        logging.debug("fetch_price err %s", e)
        return None

def fetch_orderbook(symbol: str, limit:int=50):
    try:
        path = "/api/spot/v1/market/depth"
        data = bitget_get_json(path, params={"symbol": f"{symbol}USDT", "limit": limit})
        d = data.get("data") or {}
        bids = d.get("bids", [])  # [price, size]
        asks = d.get("asks", [])
        bids_parsed = [(float(p), float(s)) for p,s in bids] if bids else []
        asks_parsed = [(float(p), float(s)) for p,s in asks] if asks else []
        bid_vol = sum(s for _,s in bids_parsed)
        ask_vol = sum(s for _,s in asks_parsed)
        return {"bids": bids_parsed, "asks": asks_parsed, "bid_vol": bid_vol, "ask_vol": ask_vol}
    except Exception as e:
        logging.debug("fetch_orderbook err %s", e)
        return {"bids": [], "asks": [], "bid_vol":0.0, "ask_vol":0.0}

def fetch_ohlcv(symbol: str, granularity:int=86400, limit:int=200):
    """
    Candle fetch from Bitget spot candles endpoint.
    Returns list oldest->newest of dicts {time,open,high,low,close,volume}
    """
    try:
        path = "/api/spot/v1/market/candles"
        data = bitget_get_json(path, params={"symbol": f"{symbol}USDT", "granularity": granularity, "limit": limit})
        arr = data.get("data") or []
        out = []
        for it in arr:
            if isinstance(it, list) and len(it) >= 6:
                ts = float(it[0])
                if ts > 1e12:
                    ts = ts/1000.0
                out.append({
                    "time": datetime.fromtimestamp(ts, tz=JST),
                    "open": float(it[1]),
                    "high": float(it[2]),
                    "low": float(it[3]),
                    "close": float(it[4]),
                    "volume": float(it[5])
                })
            elif isinstance(it, dict):
                ts = float(it.get("timestamp") or it.get("time") or it.get("id"))
                if ts > 1e12:
                    ts = ts/1000.0
                out.append({
                    "time": datetime.fromtimestamp(ts, tz=JST),
                    "open": float(it.get("open")),
                    "high": float(it.get("high")),
                    "low": float(it.get("low")),
                    "close": float(it.get("close")),
                    "volume": float(it.get("volume",0))
                })
        return list(reversed(out))
    except Exception as e:
        logging.debug("fetch_ohlcv err %s", e)
        return []

# ---- Indicators / analysis ----
def calc_atr(symbol:str, period:int=ATR_PERIOD) -> Optional[float]:
    ohl = fetch_ohlcv(symbol, granularity=86400, limit=period+2)
    if not ohl or len(ohl) < period+1:
        return None
    trs = []
    for i in range(1, len(ohl)):
        high = ohl[i]["high"]
        low  = ohl[i]["low"]
        prev_close = ohl[i-1]["close"]
        tr = max(high-low, abs(high-prev_close), abs(low-prev_close))
        trs.append(tr)
    if not trs:
        return None
    atr = sum(trs[-period:]) / period
    return float(atr)

def sma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n

def compute_1d_change_pct(symbol:str) -> Optional[float]:
    ohl = fetch_ohlcv(symbol, granularity=86400, limit=2)
    if not ohl or len(ohl) < 2:
        return None
    today = ohl[-1]["close"]
    prev = ohl[-2]["close"]
    return (today/prev - 1.0) * 100.0

def fetch_fear_and_greed():
    proxy = os.getenv("PROXY_URL", "https://api.alternative.me/fng/")
    try:
        r = requests.get(proxy, timeout=6).json()
        data = r.get("data", [{}])[0]
        return {"value": data.get("value", "N/A"), "classification": data.get("value_classification", "Unknown")}
    except Exception:
        return {"value": "N/A", "classification": "Unknown"}

def generate_ai_comment(symbol:str, price:float, fg:dict) -> Tuple[str,float]:
    """
    Build a multi-layer rule-based commentary and compute a score (0-100).
    Score components:
      - momentum: 1d change
      - volatility: ATR/price ratio
      - orderbook bias
      - trend SMA7 vs SMA25
      - fear&greed influence
    """
    pieces = []
    score = 50.0

    # Fear & Greed
    try:
        fg_val = int(fg.get("value") if isinstance(fg.get("value"), str) and fg.get("value").isdigit() else 50)
    except Exception:
        fg_val = 50
    fg_label = fg.get("classification", "Neutral")
    pieces.append(f"市場心理: {fg_label} ({fg_val})")

    # ATR
    atr = calc_atr(symbol)
    if atr:
        ratio = atr / price if price and price>0 else 0.0
        pieces.append(f"ATR(14日): {atr:.6f} ≒ {ratio*100:.2f}% of price")
        # volatility influence: higher ATR ratio penalize score slightly (risk)
        if ratio > 0.05:
            score -= 10
            pieces.append("ボラティリティ高め → リスク注意")
        elif ratio < 0.02:
            score += 5
            pieces.append("ボラ低め → エントリしやすい")
    else:
        pieces.append("ATRデータ不足")

    # Orderbook
    ob = fetch_orderbook(symbol, limit=40)
    bid_vol = ob.get("bid_vol",0.0)
    ask_vol = ob.get("ask_vol",0.0)
    if bid_vol + ask_vol > 0:
        if bid_vol > ask_vol * 1.4:
            score += 8
            pieces.append(f"板: 買い厚め (buy {bid_vol:.1f} > sell {ask_vol:.1f}) — 支えあり")
        elif ask_vol > bid_vol * 1.4:
            score -= 8
            pieces.append(f"板: 売り厚め (sell {ask_vol:.1f} > buy {bid_vol:.1f}) — 売圧注意")
        else:
            pieces.append(f"板: 拮抗 (buy {bid_vol:.1f} / sell {ask_vol:.1f})")
    else:
        pieces.append("板データ不足")

    # Momentum 1d
    ch1d = compute_1d_change_pct(symbol)
    if ch1d is not None:
        pieces.append(f"1日変化: {ch1d:+.2f}%")
        score += max(min(ch1d, 10), -10)  # +/-
    else:
        pieces.append("1日変化データ不足")

    # SMA trend
    ohl = fetch_ohlcv(symbol, granularity=86400, limit=30)
    closes = [c["close"] for c in ohl] if ohl else []
    sma7 = sma(closes, 7)
    sma25 = sma(closes, 25)
    if sma7 and sma25:
        if sma7 > sma25:
            score += 5
            pieces.append("短期SMA(7) > 長期SMA(25): 上昇トレンド")
        elif sma7 < sma25:
            score -= 5
            pieces.append("短期SMA(7) < 長期SMA(25): 下降トレンド")
        else:
            pieces.append("SMA 横ばい")
    else:
        pieces.append("チャートデータ不足")

    # Fear/greed weighting
    if fg_val >= 70:
        score -= 6
        pieces.append("強欲フェーズ: 過熱注意")
    elif fg_val <= 30:
        score += 4
        pieces.append("恐怖フェーズ: 割安探し向き")

    # clamp and compute final score 0-100
    score = max(0.0, min(100.0, score))
    commentary = "\n".join(pieces)
    return commentary, score

# ---- TP/SL computation helper ----
def compute_tp_sl_from_atr(side:str, entry_price:float, atr:float) -> Tuple[float,float]:
    if side.lower() == "long":
        tp = entry_price + TP_ATR_MULT * atr
        sl = entry_price - SL_ATR_MULT * atr
    else:
        tp = entry_price - TP_ATR_MULT * atr
        sl = entry_price + SL_ATR_MULT * atr
    return float(tp), float(sl)

# ---- Telegram helper ----
def send_telegram_html(text:str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.debug("Telegram not configured, message skipped.")
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
        logging.exception("Telegram send failed: %s", e)

# ---- Trading logic: open candidate if score and momentum pass thresholds ----
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "60.0"))

def attempt_open_candidate(symbol:str):
    price = fetch_price(symbol)
    if price is None:
        return
    atr = calc_atr(symbol)
    if atr is None:
        return
    # compute commentary & score
    fg = fetch_fear_and_greed()
    ai_comment, score = generate_ai_comment(symbol, price, fg)

    # momentum
    ch1d = compute_1d_change_pct(symbol)
    # signal logic:
    # - if 1d change >= PRICE_CHANGE_THRESHOLD_PCT and score >= SCORE_THRESHOLD => open LONG
    # - if 1d change <= -PRICE_CHANGE_THRESHOLD_PCT and score >= SCORE_THRESHOLD => open SHORT
    if ch1d is None:
        return

    if ch1d >= PRICE_CHANGE_THRESHOLD_PCT and score >= SCORE_THRESHOLD:
        side = "long"
    elif ch1d <= -PRICE_CHANGE_THRESHOLD_PCT and score >= SCORE_THRESHOLD:
        side = "short"
    else:
        return

    # compute TP/SL
    tp, sl = compute_tp_sl_from_atr(side, price, atr)
    # position size in asset units
    usd = POSITION_SIZE_USD
    amount_asset = usd / price if price and price>0 else 0.0
    # multi-step TP levels: 50%, 25%, remaining
    tp1 = tp
    tp2 = price + (tp - price) * 1.6 if side=="long" else price + (tp - price)*1.6  # heuristic second TP further
    tp3 = price + (tp - price)*2.5 if side=="long" else price + (tp - price)*2.5

    tp_levels = [tp1, tp2, tp3]

    # Place order via executor
    order = executor.place_futures_market_order(symbol, side, amount_asset, reduce_only=False)
    # Register in state (we treat as filled if paper or exchange returned)
    state.open_position(symbol, side, amount_asset, price, tp_levels, sl)

    # send telegram with rich info
    msg = f"<b>📥 New Position</b>\n"
    msg += f"<b>{symbol}</b> — <code>{side.upper()}</code>\n"
    msg += f"Entry: <code>{price:.6f}</code>  Size: <code>{amount_asset:.6f}</code>\n"
    msg += f"TP levels: <code>{tp_levels[0]:.6f}</code>, <code>{tp_levels[1]:.6f}</code>, <code>{tp_levels[2]:.6f}</code>\n"
    msg += f"SL: <code>{sl:.6f}</code>\n"
    msg += f"<b>Score:</b> <code>{score:.1f}</code>\n"
    msg += "<b>AI 分析</b>\n<pre>" + ai_comment + "</pre>"
    send_telegram_html(msg)
    logging.info("Opened %s %s (sim=%s) entry=%.6f size=%.6f score=%.1f", symbol, side, PAPER_TRADING, price, amount_asset, score)

# ---- cycle: check TP/SL, attempt openings, hourly summary ----
def check_positions_and_manage():
    """
    Called frequently (e.g. every minute) to:
     - inspect existing positions and close portions when TP/SL hit (multi-step).
     - attempt to open new candidate positions based on rules.
    """
    logging.info("=== cycle start === %s", datetime.now(JST).isoformat())
    fg = fetch_fear_and_greed()
    # check current positions
    positions = state.get_positions()
    for sym, pos in list(positions.items()):
        price = fetch_price(sym)
        if price is None:
            continue
        side = pos["side"]
        # check TP levels: when hit, close portion according to steps in order
        tps = pos.get("tp_levels", [])
        partials = pos.get("partial_steps", [0.5,0.25,0.25])
        # iterate through tps: if hit and not yet closed corresponding portion (we detect via closed_amount)
        for idx, tp in enumerate(tps):
            # decide whether this level is still active: compute how much already closed relative to expected
            # simpler: if price reached and pos still has enough amount, close portion
            if side == "long" and price >= tp and pos.get("amount",0)>1e-12:
                # portion to close:
                portion = partials[idx] if idx < len(partials) else 1.0
                trade = state.close_position(sym, price, reason=f"TP{idx+1}", portion=portion)
                if trade:
                    text = f"<b>✅ TP{idx+1} hit</b>\n<b>{sym}</b> ({side.upper()})\nEntry: <code>{trade['entry_price']:.6f}</code>\nExit: <code>{trade['exit_price']:.6f}</code>\nPnL: <code>{trade['pnl']:.6f} USDT</code>\n"
                    ai, _ = generate_ai_comment(sym, price, fg)
                    send_telegram_html(text + "<pre>" + ai + "</pre>")
                # after processing one level, break to avoid multiple closures same minute
                break
            if side == "short" and price <= tp and pos.get("amount",0)>1e-12:
                portion = partials[idx] if idx < len(partials) else 1.0
                trade = state.close_position(sym, price, reason=f"TP{idx+1}", portion=portion)
                if trade:
                    text = f"<b>✅ TP{idx+1} hit</b>\n<b>{sym}</b> ({side.upper()})\nEntry: <code>{trade['entry_price']:.6f}</code>\nExit: <code>{trade['exit_price']:.6f}</code>\nPnL: <code>{trade['pnl']:.6f} USDT</code>\n"
                    ai, _ = generate_ai_comment(sym, price, fg)
                    send_telegram_html(text + "<pre>" + ai + "</pre>")
                break
        # check SL:
        sl = pos.get("sl_price")
        if sl is not None and pos.get("amount",0)>1e-12:
            if (side=="long" and price <= sl) or (side=="short" and price >= sl):
                trade = state.close_position(sym, price, reason="SL", portion=1.0)
                if trade:
                    text = f"<b>❌ STOP LOSS hit</b>\n<b>{sym}</b> ({side.upper()})\nEntry: <code>{trade['entry_price']:.6f}</code>\nExit: <code>{trade['exit_price']:.6f}</code>\nPnL: <code>{trade['pnl']:.6f} USDT</code>\n"
                    ai, _ = generate_ai_comment(sym, price, fg)
                    send_telegram_html(text + "<pre>" + ai + "</pre>")

    # attempt new openings for monitored symbols (skip if already position)
    for sym in MONITORED_SYMBOLS:
        if state.has_position(sym):
            continue
        try:
            attempt_open_candidate(sym)
        except Exception:
            logging.exception("attempt_open_candidate failed for %s", sym)
        time.sleep(0.2)  # tiny throttle

    # update last snapshot for status endpoint
    snapshot = {
        "ts": datetime.now(JST).isoformat(),
        "positions": state.get_positions(),
        "balance": state.get_balance(),
        "win_rate": state.get_win_rate()
    }
    state.update_last_snapshot(snapshot)
    logging.info("=== cycle finished ===")

# ---- hourly summary at JST top of hour ----
def hourly_report():
    now = datetime.now(timezone.utc).astimezone(JST)
    header = f"<b>🕒 時間レポート ({now.strftime('%Y-%m-%d %H:%M JST')})</b>\n"
    header += f"<b>残高:</b> <code>{state.get_balance():.2f} USDT</code>\n"
    header += f"<b>勝率:</b> <code>{state.get_win_rate():.2f}%</code>\n"
    header += f"<b>保有数:</b> <code>{len(state.get_positions())}</code>\n\n"

    fg = fetch_fear_and_greed()
    body = ""
    pos = state.get_positions()
    if pos:
        for sym, p in pos.items():
            price = fetch_price(sym) or 0.0
            ai, score = generate_ai_comment(sym, price, fg)
            body += (
                f"<b>{sym}</b> ({p['side'].upper()})\n"
                f"Entry: <code>{p['entry_price']:.6f}</code> 現在: <code>{price:.6f}</code>\n"
                f"Size: <code>{p['amount']:.6f}</code>\n"
                f"TPs: <code>{', '.join([f'{x:.6f}' for x in p.get('tp_levels',[])])}</code>\n"
                f"SL: <code>{p.get('sl_price'):.6f}</code>\n"
                f"<b>Score:</b> <code>{score:.1f}</code>\n"
                f"<pre>{ai}</pre>\n\n"
            )
    else:
        btc_price = fetch_price("BTC") or 0.0
        ai, score = generate_ai_comment("BTC", btc_price, fg)
        body += f"保有ポジションなし\n\n<b>BTC 分析</b>\n<pre>{ai}</pre>\n"

    footer = f"\n<b>Fear&Greed:</b> {fg.get('value')} ({fg.get('classification')})\n"
    send_telegram_html(header + body + footer)

# ---- Scheduler loop ----
def scheduler_loop():
    # run cycle every minute
    schedule.every(1).minutes.do(check_positions_and_manage)
    while True:
        schedule.run_pending()
        # trigger hourly report exactly at JST minute==0
        now = datetime.now(timezone.utc).astimezone(JST)
        if now.minute == 0 and now.second < 5:
            try:
                hourly_report()
                # avoid double-run within same minute
                time.sleep(61)
            except Exception:
                logging.exception("hourly_report failed")
        time.sleep(1)

# ---- Status API (simple protected) ----
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route("/")
def root():
    return "Trend Sentinel (Bitget Futures) - status available."

@app.route("/status")
def status():
    key = request.args.get("key","")
    if key != STATUS_KEY:
        return jsonify({"error":"unauthorized"}), 401
    snap = state.get_state_snapshot()
    snap["server_time_jst"] = datetime.now(timezone.utc).astimezone(JST).isoformat()
    # attach Fear&Greed quick value
    snap["fear_greed"] = fetch_fear_and_greed()
    return jsonify(snap)

# ---- Entrypoint ----
if __name__ == "__main__":
    logging.info("Starting Trend Sentinel (Futures USDT perpetual). PAPER_TRADING=%s", PAPER_TRADING)
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
