# main.py
import os
import logging
import requests
import schedule
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from state_manager import StateManager

# --- 環境変数 / 設定 ---
JST = timezone(timedelta(hours=9))
BITGET_BASE = os.getenv("BITGET_BASE", "https://api.bitget.com")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATUS_KEY = os.getenv("STATUS_KEY", "changeme")

MONITORED_SYMBOLS = os.getenv("MONITORED_SYMBOLS", "BTC,ETH,SOL,BNB").split(",")
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "100"))  # 1ポジションに使うUSD
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "2.0"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.0"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
PRICE_CHANGE_THRESHOLD_PCT = float(os.getenv("PRICE_CHANGE_THRESHOLD_PCT", "5.0"))  # 1日変化で新規判定

PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"  # true by default

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

state = StateManager()

# --- Utilities: Bitget data fetch (synchronous, robust) ---
def bitget_get_json(path: str, params: dict = None):
    url = f"{BITGET_BASE}{path}"
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error("Bitget request failed %s %s", url, e)
        return {}

def fetch_price(symbol: str) -> Optional[float]:
    """Fetch last price from Bitget spot ticker endpoint (symbol passed like 'BTC')."""
    try:
        # Some Bitget APIs expect e.g. "BTCUSDT" or "BTC_USDT" — we use common 'symbolUSDT'
        path = "/api/spot/v1/market/ticker"
        data = bitget_get_json(path, params={"symbol": f"{symbol}USDT"})
        if not data:
            return None
        # Try common keys
        last = data.get("data", {}).get("last") or (data.get("data") and data["data"][0].get("last"))
        if last is None:
            # fallback: sometimes 'close' exists
            last = data.get("data", {}).get("close")
        return float(last) if last is not None else None
    except Exception as e:
        logging.error("fetch_price error: %s", e)
        return None

def fetch_orderbook(symbol: str, limit: int = 50) -> Dict[str, Any]:
    """Fetch orderbook (depth) from Bitget spot market depth API."""
    try:
        path = "/api/spot/v1/market/depth"
        data = bitget_get_json(path, params={"symbol": f"{symbol}USDT", "limit": limit})
        d = data.get("data") or {}
        bids = d.get("bids", [])  # list of [price, size]
        asks = d.get("asks", [])
        bids_parsed = [(float(p), float(s)) for p, s in bids] if bids else []
        asks_parsed = [(float(p), float(s)) for p, s in asks] if asks else []
        bid_vol = sum(s for _, s in bids_parsed)
        ask_vol = sum(s for _, s in asks_parsed)
        return {"bids": bids_parsed, "asks": asks_parsed, "bid_vol": bid_vol, "ask_vol": ask_vol}
    except Exception as e:
        logging.error("fetch_orderbook error: %s", e)
        return {"bids": [], "asks": [], "bid_vol": 0.0, "ask_vol": 0.0}

def fetch_ohlcv(symbol: str, granularity: int = 86400, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch candles from Bitget. Returns list of dict with keys: time, open, high, low, close, volume.
    granularity in seconds (86400 = daily).
    """
    try:
        path = "/api/spot/v1/market/candles"
        data = bitget_get_json(path, params={"symbol": f"{symbol}USDT", "granularity": granularity, "limit": limit})
        result = []
        for item in data.get("data", []):
            # The format may vary; try to parse common arrays
            try:
                # if item is array like [timestamp, open, high, low, close, volume]
                if isinstance(item, list) and len(item) >= 6:
                    ts = int(item[0])
                    # some API give ms, some s — heuristics:
                    if ts > 1e12:
                        ts = ts / 1000.0
                    dt = datetime.fromtimestamp(float(ts), tz=JST)
                    o, h, l, c, v = map(float, item[1:6])
                    result.append({"time": dt, "open": o, "high": h, "low": l, "close": c, "volume": v})
                elif isinstance(item, dict):
                    # dict style
                    ts = int(item.get("timestamp") or item.get("time") or item.get("id"))
                    if ts > 1e12:
                        ts = ts / 1000.0
                    dt = datetime.fromtimestamp(float(ts), tz=JST)
                    o = float(item.get("open")); h = float(item.get("high")); l = float(item.get("low")); c = float(item.get("close")); v = float(item.get("volume", 0))
                    result.append({"time": dt, "open": o, "high": h, "low": l, "close": c, "volume": v})
            except Exception:
                continue
        # ensure chronological order oldest->newest
        return list(reversed(result))
    except Exception as e:
        logging.error("fetch_ohlcv error: %s", e)
        return []

# --- ATR calculation ---
def calc_atr(symbol: str, period: int = ATR_PERIOD) -> Optional[float]:
    ohlcv = fetch_ohlcv(symbol, granularity=86400, limit=period + 2)
    if not ohlcv or len(ohlcv) < period + 1:
        return None
    trs = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i]["high"]
        low = ohlcv[i]["low"]
        prev_close = ohlcv[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return None
    atr = sum(trs[-period:]) / period
    return float(atr)

# --- Fear & Greed ---
def fetch_fear_and_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()
        return r.get("data", [{}])[0]
    except Exception as e:
        logging.debug("fetch_fear_and_greed failed: %s", e)
        return {"value": "N/A", "value_classification": "Unknown"}

# --- AI风コメント（ルールベースの多層分析） ---
def fetch_trend(symbol: str, short: int = 7, long: int = 25) -> str:
    ohlcv = fetch_ohlcv(symbol, granularity=86400, limit=long + 1)
    if not ohlcv or len(ohlcv) < long:
        return "不明"
    closes = [c["close"] for c in ohlcv]
    sma_s = sum(closes[-short:]) / short
    sma_l = sum(closes[-long:]) / long
    if sma_s > sma_l:
        return "上昇基調 📈"
    elif sma_s < sma_l:
        return "下落基調 📉"
    else:
        return "横ばい 😐"

def generate_ai_comment(symbol: str, price: float, fg: dict) -> str:
    fg_value = int(fg.get("value") if fg.get("value") and fg.get("value").isdigit() else 50)
    fg_label = fg.get("value_classification", "Neutral")

    if fg_value < 30:
        fg_comment = f"市場: 恐怖モード ({fg_label}) — ディップ狙いの可能性あり。📉"
    elif fg_value > 70:
        fg_comment = f"市場: 強欲モード ({fg_label}) — 過熱注意。🔥"
    else:
        fg_comment = f"市場: 中立 ({fg_label}) — 大きな急変は起きにくいかも。"

    atr = calc_atr(symbol)
    if atr and price and price > 0:
        ratio = atr / price
        if ratio > 0.05:
            vol_comment = f"ボラ: ATR={atr:.3f} (高ボラティリティ)。短期で乱高下しやすい。"
        elif ratio < 0.02:
            vol_comment = f"ボラ: ATR={atr:.3f} (低ボラ)。落ち着いた推移が想定される。"
        else:
            vol_comment = f"ボラ: ATR={atr:.3f} (中程度)。"
    else:
        vol_comment = "ATRデータ不足。"

    ob = fetch_orderbook(symbol, limit=50)
    ob_comment = ""
    try:
        if ob["bid_vol"] > ob["ask_vol"] * 1.5:
            ob_comment = f"板: 買い厚め (buy={ob['bid_vol']:.1f} vs sell={ob['ask_vol']:.1f}) — 下支えあり。"
        elif ob["ask_vol"] > ob["bid_vol"] * 1.5:
            ob_comment = f"板: 売り厚め (buy={ob['bid_vol']:.1f} vs sell={ob['ask_vol']:.1f}) — 売圧注意。"
        else:
            ob_comment = f"板: 拮抗 (buy={ob['bid_vol']:.1f} / sell={ob['ask_vol']:.1f})"
    except Exception:
        ob_comment = "板データ不足。"

    trend = fetch_trend(symbol)

    return f"{fg_comment}\n{vol_comment}\n{ob_comment}\nトレンド: {trend}"

# --- Position helper: compute TP/SL from ATR multipliers ---
def compute_tp_sl(side: str, entry_price: float, atr: float) -> (float, float):
    """Return (take_profit, stop_loss). For long: tp = entry + TP_ATR_MULT*atr, sl = entry - SL_ATR_MULT*atr"""
    if side.lower() == "long":
        tp = entry_price + TP_ATR_MULT * atr
        sl = entry_price - SL_ATR_MULT * atr
    else:
        # short: TP below entry
        tp = entry_price - TP_ATR_MULT * atr
        sl = entry_price + SL_ATR_MULT * atr
    return float(tp), float(sl)

# --- Telegram msg (HTML) ---
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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error("send_telegram error: %s", e)

# --- Simple rule to create signals (demo). Replace with real scorer in production ---
def compute_1d_change_pct(symbol: str) -> Optional[float]:
    ohlcv = fetch_ohlcv(symbol, granularity=86400, limit=2)
    if not ohlcv or len(ohlcv) < 2:
        return None
    today = ohlcv[-1]["close"]
    prev = ohlcv[-2]["close"]
    return (today / prev - 1.0) * 100.0

# --- Trading cycle ---
def run_trading_cycle():
    logging.info("=== Trading cycle start (%s) ===", datetime.now(JST).isoformat())
    fg = fetch_fear_and_greed()
    snapshot = {"timestamp": datetime.now(JST).isoformat(), "symbols": {}}

    for sym in MONITORED_SYMBOLS:
        sym = sym.strip().upper()
        try:
            price = fetch_price(sym)
            if price is None:
                logging.info("price missing for %s, skip", sym)
                continue

            snapshot["symbols"][sym] = {"price": price}

            # Check existing position
            if state.has_position(sym):
                pos = state.get_positions().get(sym)
                side = pos["side"]
                tp = float(pos["take_profit"])
                sl = float(pos["stop_loss"])
                # Check TP/SL by price reach
                if side.lower() == "long":
                    if price >= tp:
                        rec = state.close_position(sym, exit_price=price, reason="TP")
                        msg = (
                            f"<b>✅ 利確 (TP)</b>\n"
                            f"<b>{sym}</b> ({side.upper()})\n"
                            f"Entry: <code>{rec['entry_price']:.6f}</code>\n"
                            f"Exit: <code>{rec['exit_price']:.6f}</code>\n"
                            f"PnL: <code>{rec['pnl']:.6f} USDT</code>\n"
                            f"Reason: {rec['reason']}\n"
                        )
                        # add AI analysis
                        ai = generate_ai_comment(sym, price, fg)
                        send_telegram_html(msg + "<pre>" + ai + "</pre>")
                    elif price <= sl:
                        rec = state.close_position(sym, exit_price=price, reason="SL")
                        msg = (
                            f"<b>❌ 損切 (SL)</b>\n"
                            f"<b>{sym}</b> ({side.upper()})\n"
                            f"Entry: <code>{rec['entry_price']:.6f}</code>\n"
                            f"Exit: <code>{rec['exit_price']:.6f}</code>\n"
                            f"PnL: <code>{rec['pnl']:.6f} USDT</code>\n"
                            f"Reason: {rec['reason']}\n"
                        )
                        ai = generate_ai_comment(sym, price, fg)
                        send_telegram_html(msg + "<pre>" + ai + "</pre>")
                else:  # short
                    if price <= tp:
                        rec = state.close_position(sym, exit_price=price, reason="TP")
                        msg = (
                            f"<b>✅ 利確 (TP)</b>\n"
                            f"<b>{sym}</b> ({side.upper()})\n"
                            f"Entry: <code>{rec['entry_price']:.6f}</code>\n"
                            f"Exit: <code>{rec['exit_price']:.6f}</code>\n"
                            f"PnL: <code>{rec['pnl']:.6f} USDT</code>\n"
                        )
                        ai = generate_ai_comment(sym, price, fg)
                        send_telegram_html(msg + "<pre>" + ai + "</pre>")
                    elif price >= sl:
                        rec = state.close_position(sym, exit_price=price, reason="SL")
                        msg = (
                            f"<b>❌ 損切 (SL)</b>\n"
                            f"<b>{sym}</b> ({side.upper()})\n"
                            f"Entry: <code>{rec['entry_price']:.6f}</code>\n"
                            f"Exit: <code>{rec['exit_price']:.6f}</code>\n"
                            f"PnL: <code>{rec['pnl']:.6f} USDT</code>\n"
                        )
                        ai = generate_ai_comment(sym, price, fg)
                        send_telegram_html(msg + "<pre>" + ai + "</pre>")

            else:
                # No position: generate simple candidate rule using 1d change pct
                change_1d = compute_1d_change_pct(sym)
                if change_1d is None:
                    continue
                # Simple signals: momentum > threshold -> LONG, momentum < -threshold -> SHORT
                if change_1d >= PRICE_CHANGE_THRESHOLD_PCT:
                    # open long
                    atr = calc_atr(sym)
                    if atr is None:
                        logging.debug("ATR not available for %s, skipping open", sym)
                        continue
                    tp, sl = compute_tp_sl("long", entry_price=price, atr=atr)
                    # calculate position size in asset units
                    max_usd = POSITION_SIZE_USD
                    size_asset = max_usd / price
                    if PAPER_TRADING:
                        state.open_position(sym, "long", entry_price=price, amount=size_asset, take_profit=tp, stop_loss=sl)
                        msg = (
                            f"<b>📥 新規ポジション (SIM)</b>\n"
                            f"<b>{sym}</b> LONG\n"
                            f"Entry: <code>{price:.6f}</code>\n"
                            f"Size(assets): <code>{size_asset:.6f}</code>\n"
                            f"TP: <code>{tp:.6f}</code>\n"
                            f"SL: <code>{sl:.6f}</code>\n"
                        )
                        ai = generate_ai_comment(sym, price, fg)
                        send_telegram_html(msg + "<pre>" + ai + "</pre>")
                    else:
                        # Real order placement logic should be here using TradingExecutor
                        logging.info("Real order flow not implemented in this demo.")
                elif change_1d <= -PRICE_CHANGE_THRESHOLD_PCT:
                    # open short (futures). For paper trading we simulate.
                    atr = calc_atr(sym)
                    if atr is None:
                        continue
                    tp, sl = compute_tp_sl("short", entry_price=price, atr=atr)
                    size_asset = POSITION_SIZE_USD / price
                    if PAPER_TRADING:
                        state.open_position(sym, "short", entry_price=price, amount=size_asset, take_profit=tp, stop_loss=sl)
                        msg = (
                            f"<b>📥 新規ポジション (SIM)</b>\n"
                            f"<b>{sym}</b> SHORT\n"
                            f"Entry: <code>{price:.6f}</code>\n"
                            f"Size(assets): <code>{size_asset:.6f}</code>\n"
                            f"TP: <code>{tp:.6f}</code>\n"
                            f"SL: <code>{sl:.6f}</code>\n"
                        )
                        ai = generate_ai_comment(sym, price, fg)
                        send_telegram_html(msg + "<pre>" + ai + "</pre>")

        except Exception as e:
            logging.exception("Error processing symbol %s: %s", sym, e)

        # small sleep to avoid blasting API
        time.sleep(0.2)

    # Update last snapshot in state for status endpoint
    state.update_last_snapshot(snapshot)
    logging.info("=== Trading cycle finished ===")

# --- hourly report (JST top of hour) ---
def hourly_report():
    fg = fetch_fear_and_greed()
    balance = state.get_balance()
    positions = state.get_positions()
    win_rate = state.get_win_rate()

    header = f"<b>🕒 定期レポート ({datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')})</b>\n"
    header += f"<b>残高:</b> <code>{balance:.2f} USDT</code>\n"
    header += f"<b>勝率:</b> <code>{win_rate:.2f}%</code>\n\n"

    body = ""
    if positions:
        body += "<b>保有ポジション</b>\n"
        for sym, pos in positions.items():
            price = fetch_price(sym) or 0.0
            ai = generate_ai_comment(sym, price, fg)
            body += (
                f"<b>{sym}</b> ({pos['side'].upper()})\n"
                f"Entry: <code>{pos['entry_price']:.6f}</code>  現在: <code>{price:.6f}</code>\n"
                f"TP: <code>{pos['take_profit']:.6f}</code>  SL: <code>{pos['stop_loss']:.6f}</code>\n"
                f"{ai}\n\n"
            )
    else:
        # no positions: show BTC analysis
        btc_price = fetch_price("BTC") or 0.0
        ai = generate_ai_comment("BTC", btc_price, fg)
        body += f"保有ポジション: なし\n\n<b>BTC 分析</b>\n{ai}\n"

    footer = f"\n<b>Fear & Greed:</b> {fg.get('value')} ({fg.get('value_classification')})\n"
    msg = header + body + footer
    send_telegram_html(msg)

# --- scheduler helper: we run trading cycle every minute, but hourly report at JST minute==0 ---
def scheduler_loop():
    schedule.every(1).minutes.do(run_trading_cycle)
    # we'll call hourly_report from a minute job when JST minute == 0
    while True:
        # run due jobs (trading cycle scheduled)
        schedule.run_pending()
        # manual check for JST top of hour to run hourly_report exactly once when minute==0
        now = datetime.now(timezone.utc).astimezone(JST)
        if now.minute == 0 and now.second < 5:
            try:
                logging.info("Triggering hourly_report (JST top of hour).")
                hourly_report()
                # sleep ~60s to avoid double-run within same minute
                time.sleep(61)
            except Exception as e:
                logging.exception("hourly_report failed: %s", e)
        time.sleep(1)

# --- Status endpoint ---
from flask import Flask, request, jsonify
api = Flask(__name__)

@api.route("/")
def root():
    return "Trend Sentinel Bot (status) - protected endpoints available."

@api.route("/status")
def status():
    key = request.args.get("key", "")
    if key != STATUS_KEY:
        return jsonify({"error": "unauthorized"}), 401
    snap = state.get_state_snapshot()
    # attach Fear&Greed quick
    snap["fear_greed"] = fetch_fear_and_greed()
    snap["server_time_jst"] = datetime.now(JST).isoformat()
    return jsonify(snap)

# --- Entrypoint ---
if __name__ == "__main__":
    logging.info("Starting Trend Sentinel Bot (ATR TP/SL enabled). Paper trading: %s", PAPER_TRADING)
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    api.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
