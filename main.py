# main.py
import os
import time
import math
import logging
import threading
import schedule
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

import ccxt

from state_manager import StateManager
from trading_executor import TradingExecutor
from backtester import Backtester

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("trend-sentinel")

# --- Config from env ---
JST = timezone(timedelta(hours=9))
PAPER_TRADING = os.getenv("PAPER_TRADING", "True") in ["True", "true", "1"]
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "100"))
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "2.0"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.0"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
MONITORED_TOP_N = int(os.getenv("MONITORED_TOP_N", "30"))
BACKTEST_CANDIDATE_CANDLES = int(os.getenv("BACKTEST_CANDIDATE_CANDLES", "1000"))
STATUS_KEY = os.getenv("STATUS_KEY", "changeme")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# --- State / Executor ---
state = StateManager()
executor = TradingExecutor()
exchange = executor.exchange  # ccxt exchange instance

# --- Utilities ---
def send_telegram_html(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        logger.debug("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.warning("Failed to send telegram: %s", e)

def fetch_fear_and_greed():
    proxy = os.getenv("PROXY_URL", "https://api.alternative.me/fng/")
    try:
        r = requests.get(proxy, timeout=8).json()
        return r.get("data", [{}])[0]
    except Exception:
        return {"value": "N/A", "value_classification": "Unknown"}

def calc_atr_from_ohlcv(ohlcv: List[List[float]], period: int = ATR_PERIOD) -> float:
    if len(ohlcv) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(ohlcv)):
        high = float(ohlcv[i][2]); low = float(ohlcv[i][3]); prev_close = float(ohlcv[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    atr = sum(trs[-period:]) / period
    return float(atr)

def analyze_symbol(symbol: str) -> Dict[str, Any]:
    """
    取得: ticker, ohlcv (daily), orderbook
    分析: ATR, orderbook imbalance, 1h/24h change etc.
    スコアを返す（0..100）
    """
    try:
        # use futures symbol format like 'BTC/USDT:USDT' in this code
        # ensure market loaded
        if not exchange:
            return {"error": "exchange_not_initialized"}
        # fetch ticker
        ticker = exchange.fetch_ticker(symbol)
        last = float(ticker.get("last") or ticker.get("close") or 0.0)
        # fetch orderbook
        ob = exchange.fetch_order_book(symbol, limit=50)
        bid_vol = sum([b[1] for b in ob.get("bids", [])])
        ask_vol = sum([a[1] for a in ob.get("asks", [])])
        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-9)
        # fetch OHLCV for ATR (daily)
        ohlcv_daily = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=ATR_PERIOD + 5)
        atr = calc_atr_from_ohlcv(ohlcv_daily, period=ATR_PERIOD) if ohlcv_daily else 0.0
        # price changes (1h and 24h approximate)
        ohlcv_1h = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=25)
        change_1h = ((ohlcv_1h[-1][4] / ohlcv_1h[-2][4] - 1.0) * 100.0) if len(ohlcv_1h) >= 2 else 0.0
        # 24h change from ticker if available
        change_24h = ticker.get("percentage") or 0.0

        # score build (simple weighted)
        score = 0.0
        # momentum
        score += max(0.0, min(30.0, change_24h))  # positive 24h adds up to 30
        score += max(0.0, min(20.0, change_1h * 2.0))  # 1h influence up to 20
        # volume/imbalance
        if imbalance > 0.2:
            score += 15.0
        elif imbalance < -0.2:
            score -= 10.0
        # volatility preference: medium volatility preferred
        if atr and last:
            ratio = atr / last
            if 0.005 < ratio < 0.04:
                score += 20.0
            elif ratio < 0.005:
                score += 5.0
            else:
                score -= 5.0
        # clamp
        score = max(-100.0, min(100.0, score))
        # gather analysis comment (AI風、ルールベース)
        fg = fetch_fear_and_greed()
        fg_v = fg.get("value", "N/A")
        fg_label = fg.get("value_classification", "Unknown")
        vol_comment = f"ATR={atr:.6f}" if atr else "ATRデータ不足"
        ob_comment = f"bid_vol={bid_vol:.3f} / ask_vol={ask_vol:.3f} (imbalance={imbalance:.3f})"
        trend = "上昇" if change_24h and float(change_24h) > 0 else ("下落" if change_24h and float(change_24h) < 0 else "横ばい")
        comment = (
            f"<b>{symbol} 分析</b>\n"
            f"価格: <code>{last:.6f}</code>\n"
            f"24h変化: <code>{change_24h}</code>%  1h変化: <code>{change_1h:.2f}</code>%\n"
            f"市場心理(F&G): {fg_label} ({fg_v})\n"
            f"{vol_comment}\n"
            f"{ob_comment}\n"
            f"トレンド: {trend}\n"
            f"スコア(0-100): <code>{max(0, int(score))}</code>\n"
        )
        return {"symbol": symbol, "price": last, "atr": atr, "imbalance": imbalance, "score": max(0, int(score)), "comment": comment, "ohlcv_daily": ohlcv_daily, "ohlcv_1h": ohlcv_1h, "orderbook": ob, "ticker": ticker}
    except Exception as e:
        logger.exception("analyze_symbol error %s %s", symbol, e)
        return {"symbol": symbol, "error": str(e)}

def select_top_by_volume(n=MONITORED_TOP_N) -> List[str]:
    """
    Bitgetの先物マーケットから USDT 無期限 ペアを取り、出来高順に上位Nを返す。
    ccxt.exchange.fetch_tickers() を使う。シンボル形式は exchange が返すフォーマットをそのまま使う。
    """
    if not exchange:
        return []
    try:
        tickers = exchange.fetch_tickers()
        # filter perp USDT pairs - many exchanges use ':USDT' suffix, we accept any containing 'USDT'
        candidates = []
        for s, tk in tickers.items():
            if "USDT" in s and ":" in s:  # keep pairs like 'BTC/USDT:USDT'
                # prefer those with quoteVolume if present
                vol = tk.get("quoteVolume") or tk.get("baseVolume") or 0.0
                candidates.append((s, float(vol or 0.0)))
        # sort desc
        candidates.sort(key=lambda x: x[1], reverse=True)
        top = [c[0] for c in candidates[:n]]
        return top
    except Exception as e:
        logger.warning("select_top_by_volume failed: %s", e)
        return []

def compute_position_size_usd(balance: float, risk_alloc=0.01) -> float:
    """
    単純: 残高に対して一定の割合を使う or fixed POSITION_SIZE_USD env override.
    """
    env_size = POSITION_SIZE_USD
    # prefer env fixed size for determinism
    return float(env_size)

def run_backtest_on_symbol(symbol: str, timeframe="1h", limit=BACKTEST_CANDIDATE_CANDLES) -> dict:
    """
    指定シンボルの過去OHLCVを取り、バックテストする（Backtester）。
    """
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        bt = Backtester(ohlcv)
        res = bt.run_rule_sim(atr_period=ATR_PERIOD, tp_mult=TP_ATR_MULT, sl_mult=SL_ATR_MULT, position_usd=POSITION_SIZE_USD, initial_balance=state.get_balance())
        return res
    except Exception as e:
        logger.warning("backtest failed for %s: %s", symbol, e)
        return {}

def attempt_open_position(candidate: dict):
    """
    候補 (from analyze_symbol) に対してバックテスト→ if metrics good -> open
    """
    symbol = candidate["symbol"]
    price = candidate["price"]
    atr = candidate.get("atr") or 0.0
    score = candidate.get("score", 0)

    # run backtest and check PF / Sharpe / win_rate threshold
    bt = run_backtest_on_symbol(symbol, timeframe="1h", limit=BACKTEST_CANDIDATE_CANDLES)
    # basic acceptance rules:
    accept = False
    if bt:
        win_rate = bt.get("win_rate", 0.0) or 0.0
        pf = bt.get("profit_factor") or 0.0
        sharpe = bt.get("sharpe") or 0.0
        # if sample size small or negative metrics, reject
        if win_rate >= 40 and (pf is None or pf >= 1.0) and (sharpe is None or (sharpe and sharpe > 0.2)):
            accept = True
    else:
        # no backtest data -> fallback on score & ATR
        if score >= 60 and atr and price:
            accept = True

    if not accept:
        logger.info("Candidate %s rejected by backtest/filters: score=%s bt=%s", symbol, score, bt)
        return None

    # compute TP/SL from ATR
    tp, sl = (price + TP_ATR_MULT * atr, price - SL_ATR_MULT * atr) if score >= 50 else (price + TP_ATR_MULT * atr * 0.8, price - SL_ATR_MULT * atr * 0.8)
    # compute size asset
    usd_size = compute_position_size_usd(state.get_balance())
    size_asset = usd_size / price if price > 0 else 0.0

    # round to exchange precision and set leverage
    try:
        executor.set_leverage(symbol, leverage=10)
    except Exception:
        pass

    # open market order (paper or real)
    try:
        order = executor.create_market_order(symbol, "long" if candidate["score"] >= 50 else "short", size_asset, reduce_only=False)
    except Exception as e:
        logger.error("Order creation failed for %s: %s", symbol, e)
        return None

    # register in state
    state.open_position(symbol, "long" if candidate["score"] >= 50 else "short", size_asset, price, tp, sl, meta={"backtest": bt, "score": candidate["score"]})
    # send telegram
    msg = (
        f"<b>📥 新規ポジション</b>\n"
        f"<b>{symbol}</b>\n"
        f"Entry: <code>{price:.6f}</code>\n"
        f"Size(asset): <code>{size_asset:.6f}</code>\n"
        f"TP: <code>{tp:.6f}</code>  SL: <code>{sl:.6f}</code>\n"
        f"Score: <code>{candidate['score']}</code>\n"
        f"バックテスト勝率: <code>{bt.get('win_rate')}</code> PF: <code>{bt.get('profit_factor')}</code>\n"
    )
    # Add AI style rule-based comment
    ai_comment = candidate.get("comment", "")
    send_telegram_html(msg + "<pre>" + ai_comment + "</pre>")
    return {"order": order, "state": state.get_position(symbol)}

def check_and_close_positions():
    """
    全ポジションをチェックし TP/SL 到達で決済（段階決済は簡易実装）
    """
    positions = state.get_positions()
    if not positions:
        return
    for sym, pos in list(positions.items()):
        try:
            ticker = exchange.fetch_ticker(sym)
            price = float(ticker.get("last") or ticker.get("close") or 0.0)
            side = pos["side"]
            tp = float(pos["take_profit"])
            sl = float(pos["stop_loss"])
            size_asset = float(pos["size_asset"])
            if side == "long":
                if price >= tp:
                    # staged close: 50% then 25% then rest (simplified: close all)
                    # here we implement full close via executor
                    executor.close_position_market(sym, side, size_asset)
                    rec = state.close_position(sym, price, reason="TP")
                    send_telegram_html(f"<b>✅ 決済(TP)</b>\n<code>{sym}</code>\nPnL: <code>{rec['pnl']:.2f} USDT</code>")
                elif price <= sl:
                    executor.close_position_market(sym, side, size_asset)
                    rec = state.close_position(sym, price, reason="SL")
                    send_telegram_html(f"<b>❌ 損切(SL)</b>\n<code>{sym}</code>\nPnL: <code>{rec['pnl']:.2f} USDT</code>")
            else:  # short
                if price <= tp:
                    executor.close_position_market(sym, side, size_asset)
                    rec = state.close_position(sym, price, reason="TP")
                    send_telegram_html(f"<b>✅ 決済(TP)</b>\n<code>{sym}</code>\nPnL: <code>{rec['pnl']:.2f} USDT</code>")
                elif price >= sl:
                    executor.close_position_market(sym, side, size_asset)
                    rec = state.close_position(sym, price, reason="SL")
                    send_telegram_html(f"<b>❌ 損切(SL)</b>\n<code>{sym}</code>\nPnL: <code>{rec['pnl']:.2f} USDT</code>")
        except Exception as e:
            logger.exception("check_and_close_positions error %s: %s", sym, e)

# --- Main cycle ---
def run_cycle():
    logger.info("=== cycle start === %s", datetime.now(JST).isoformat())
    # 1) select top N futures by volume
    symbols = select_top_by_volume(MONITORED_TOP_N)
    logger.info("Monitoring %d symbols", len(symbols))
    # 2) analyze all symbols
    candidates = []
    for s in symbols:
        try:
            candidate = analyze_symbol(s)
            if candidate.get("error"):
                continue
            # keep candidates above a score (e.g., >=50)
            if candidate.get("score", 0) >= 50:
                candidates.append(candidate)
        except Exception as e:
            logger.exception("symbol analysis failed %s: %s", s, e)
        time.sleep(0.1)

    # 3) For each candidate run backtester and attempt open
    for cand in candidates:
        try:
            attempt_open_position(cand)
            time.sleep(0.5)
        except Exception as e:
            logger.exception("attempt_open_position failed %s: %s", cand.get("symbol"), e)

    # 4) Check existing positions for TP/SL
    try:
        check_and_close_positions()
    except Exception as e:
        logger.exception("check_and_close_positions failed: %s", e)

    # 5) Update snapshot state for /status
    snapshot = {
        "timestamp": datetime.now(JST).isoformat(),
        "monitored": symbols,
        "candidates": [c["symbol"] for c in candidates],
        "balance": state.get_balance(),
        "positions": state.get_positions(),
        "stats": state.get_stats()
    }
    state.update_last_snapshot(snapshot)
    logger.info("=== cycle finished === %s", datetime.now(JST).isoformat())

# --- Scheduler: run every 1 minute but real trading may be limited by rules ---
def scheduler_loop():
    schedule.every(1).minutes.do(run_cycle)
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- Status API (Flask) ---
from flask import Flask, request, jsonify, render_template_string
app = Flask(__name__)

@app.route("/")
def root():
    return "Trend Sentinel (Bitget Futures) - status available."

@app.route("/status")
def status():
    key = request.args.get("key", "")
    if key != STATUS_KEY:
        return jsonify({"error": "unauthorized"}), 401
    snap = state.get_state_snapshot()
    snap["server_time_jst"] = datetime.now(JST).isoformat()
    return jsonify(snap)

if __name__ == "__main__":
    logger.info("Starting Trend Sentinel (Bitget Futures). PAPER_TRADING=%s", PAPER_TRADING)
    # start scheduler thread
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    # run webserver
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
