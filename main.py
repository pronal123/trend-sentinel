# main.py
import os
import logging
import time
import math
import threading
import schedule
import requests
import ccxt

# ===============================
#  StateManager クラス  ← ここに追加
# ===============================
class StateManager:
    def __init__(self):
        self.positions = []
        self.balance = None
        self.last_snapshot = None

    def set_positions(self, positions):
        self.positions = positions

    def get_positions(self):
        return self.positions

    def set_balance(self, balance):
        self.balance = balance

    def get_balance(self):
        return self.balance

    def update_last_snapshot(self, snapshot, balance, positions):
        """最新のスナップショット・残高・ポジションを保存"""
        self.last_snapshot = {
            "snapshot": snapshot,
            "balance": balance,
            "positions": positions
        }

    def get_last_snapshot(self):
        return self.last_snapshot


# ===============================
#  Bitget 初期化
# ===============================
# --- Bitget SPOT ---
bitget_spot = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_SPOT"),
    "secret": os.getenv("BITGET_API_SECRET_SPOT"),
    "password": os.getenv("BITGET_API_PASSPHRASE_SPOT"),
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})
logging.info("Initialized ccxt.bitget for spot.")

# --- Bitget FUTURES ---
bitget_futures = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API_KEY_FUTURES"),
    "secret": os.getenv("BITGET_API_SECRET_FUTURES"),
    "password": os.getenv("BITGET_API_PASSPHRASE_FUTURES"),
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}  # ← 永続先物
})
logging.info("Initialized ccxt.bitget for futures.")


# StateManager インスタンスを作成
state = StateManager()


from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple

import ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from state_manager import StateManager
from trading_executor import TradingExecutor

load_dotenv()

# -------- CONFIG ----------
JST = timezone(timedelta(hours=9))
BITGET_API_KEY = os.getenv("BITGET_API_KEY_FUTURES", "")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET_FUTURES", "")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE_FUTURES", "")
PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"
MONITORED_TOP_N = int(os.getenv("MONITORED_TOP_N", "30"))
POSITION_USD = float(os.getenv("POSITION_SIZE_USD", "100"))
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "2.0"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.0"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
STATUS_KEY = os.getenv("STATUS_KEY", "changeme")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# external
FEAR_GREED_URL = os.getenv("PROXY_URL", "https://api.alternative.me/fng/")

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# state and executor
state = StateManager()
executor = TradingExecutor(state)

# ccxt client for market data (no API keys needed for public data)
ccxt_client = ccxt.bitget({
    "enableRateLimit": True,
})

app = Flask(__name__)

# ---------------- helpers ----------------
def utcnow_jst_iso():
    return datetime.now(timezone.utc).astimezone(JST).isoformat()

def send_telegram_html(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.debug("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error("send_telegram error: %s", e)

# fetch Fear & Greed
def fetch_fear_and_greed() -> Dict[str, Any]:
    try:
        r = requests.get(FEAR_GREED_URL, timeout=8).json()
        return r.get("data", [{}])[0]
    except Exception:
        return {"value": "N/A", "value_classification": "Unknown"}

# get top volume symbols from Bitget futures markets
def fetch_top_symbols(limit: int = MONITORED_TOP_N) -> List[str]:
    try:
        markets = ccxt_client.fetch_markets()
        # filter USDT perpetual / swap markets
        swaps = [m for m in markets if m.get("quote") == "USDT" and (m.get("type") in (None, "swap", "future") or "USDT" in (m.get("symbol","")))]
        # get by quoteVolume24h if available
        swaps_sorted = sorted(swaps, key=lambda m: float(m.get("info", {}).get("volumeUsd24h", 0) or 0), reverse=True)
        res = []
        for m in swaps_sorted:
            sym = m.get("symbol")
            # normalize to base like 'BTC'
            if "/" in sym:
                base = sym.split("/")[0]
            else:
                base = sym.replace("USDT:USDT", "").replace("USDT", "").replace(":USDT", "")
            res.append(base)
            if len(res) >= limit:
                break
        if not res:
            # fallback static
            res = ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","DOT","AVAX","MATIC"][:limit]
        return list(dict.fromkeys([s.upper() for s in res]))  # unique preserve order
    except Exception:
        return ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","DOT","AVAX","MATIC"][:limit]

def symbol_market_ccxt(symbol: str) -> str:
    return f"{symbol}/USDT:USDT"

# OHLCV fetch via ccxt for futures/swap
def fetch_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 1000) -> List[List[Any]]:
    market_sym = symbol_market_ccxt(symbol)
    try:
        # ccxt expects timeframe like '1m','1h','1d'
        ohlcv = ccxt_client.fetch_ohlcv(market_sym, timeframe=timeframe, limit=limit)
        return ohlcv
    except Exception as e:
        logging.debug("fetch_ohlcv failed %s %s", symbol, e)
        return []

def calc_atr_from_ohlcv(ohlcv: List[List[Any]], period: int = ATR_PERIOD) -> float:
    # ohlcv rows: [ts, open, high, low, close, volume]
    if not ohlcv or len(ohlcv) < period + 1:
        return 0.0
    highs = np.array([r[2] for r in ohlcv])
    lows = np.array([r[3] for r in ohlcv])
    closes = np.array([r[4] for r in ohlcv])
    trs = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    atr = np.mean(trs[-period:])
    return float(atr)

def fetch_orderbook(symbol: str, depth: int = 50) -> Dict[str, Any]:
    market_sym = symbol_market_ccxt(symbol)
    try:
        ob = ccxt_client.fetch_order_book(market_sym, limit=depth)
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        bid_vol = sum([b[1] for b in bids])
        ask_vol = sum([a[1] for a in asks])
        return {"bids": bids, "asks": asks, "bid_vol": bid_vol, "ask_vol": ask_vol}
    except Exception as e:
        logging.debug("fetch_orderbook failed %s", e)
        return {"bids": [], "asks": [], "bid_vol": 0.0, "ask_vol": 0.0}

def dynamic_leverage(balance: float, atr: float, price: float) -> int:
    """
    残高とボラティリティに応じてレバレッジを決定する
    balance: USDT 残高
    atr:     ATR 値
    price:   現在価格
    """
    # --- 残高ベース調整 ---
    if balance < 500:
        lev_by_balance = 10
    elif balance < 2000:
        lev_by_balance = 7
    elif balance < 10000:
        lev_by_balance = 5
    else:
        lev_by_balance = 3

    # --- ボラティリティ調整 ---
    vol_ratio = atr / max(price, 1e-9)
    if vol_ratio > 0.05:   # ATRが価格の5%以上 → 超高ボラ
        lev_by_vol = 2
    elif vol_ratio > 0.03: # 高ボラ
        lev_by_vol = 3
    elif vol_ratio > 0.015: # 中ボラ
        lev_by_vol = 5
    else:                  # 低ボラ
        lev_by_vol = 7

    # --- 最終レバレッジは balance側とvol側の最小値を採用 ---
    leverage = min(lev_by_balance, lev_by_vol)
    return max(1, leverage)  # 1倍未満にならないよう制限

# AI-style comment generation (rule-based multi-layer)
def generate_ai_comment(symbol: str, price: float, atr: float, ob: Dict[str,Any], fg: Dict[str,Any], ohlcv_recent) -> str:
    parts = []
    # Fear & greed
    fg_val = fg.get("value")
    fg_label = fg.get("value_classification", "Unknown")
    parts.append(f"市場心理: {fg_label} ({fg_val})")

    # ATR
    if atr and price:
        ratio = atr / max(1e-9, price)
        if ratio > 0.05:
            parts.append(f"ボラティリティ: 高い (ATR={atr:.4f}, price={price:.4f})")
        elif ratio < 0.02:
            parts.append(f"ボラティリティ: 低い (ATR={atr:.4f})")
        else:
            parts.append(f"ボラティリティ: 中程度 (ATR={atr:.4f})")
    else:
        parts.append("ATRデータ不足")

    # orderbook thickness
    bid_vol = ob.get("bid_vol", 0.0)
    ask_vol = ob.get("ask_vol", 0.0)
    if bid_vol > ask_vol * 1.5:
        parts.append(f"板: 買い厚め (buy={bid_vol:.1f} / sell={ask_vol:.1f}) — 下支えあり")
    elif ask_vol > bid_vol * 1.5:
        parts.append(f"板: 売り厚め (buy={bid_vol:.1f} / sell={ask_vol:.1f}) — 売圧注意")
    else:
        parts.append(f"板: 拮抗 (buy={bid_vol:.1f} / sell={ask_vol:.1f})")

    # simple trend on recent closes
    try:
        closes = [r[4] for r in ohlcv_recent[-50:]] if ohlcv_recent else []
        if len(closes) >= 10:
            sma5 = np.mean(closes[-5:])
            sma20 = np.mean(closes[-20:]) if len(closes)>=20 else np.mean(closes)
            if sma5 > sma20:
                parts.append("短期トレンド: 上昇基調 📈")
            elif sma5 < sma20:
                parts.append("短期トレンド: 下落基調 📉")
            else:
                parts.append("短期トレンド: 横ばい")
        else:
            parts.append("チャートデータ不足")
    except Exception:
        parts.append("チャート分析エラー")

    # Score synthesis (simple weighted)
    score = 50.0
    if fg_val and str(fg_val).isdigit():
        v = int(fg_val)
        # higher FG -> more risk for longs
        score += (50 - v) * -0.2  # if FG high reduce score slightly
    # ATR effect
    if atr and price:
        r = atr / max(1e-9, price)
        if r < 0.02:
            score += 5
        elif r > 0.05:
            score -= 5
    # orderbook effect
    if bid_vol > ask_vol * 1.5:
        score += 5
    elif ask_vol > bid_vol * 1.5:
        score -= 5
    # normalize
    score = max(0, min(100, score))
    parts.append(f"総合スコア: {score:.1f}/100")

    return ("\n".join(parts), score)

# ---------------- Backtester (simple) ----------------
def run_backtest_for_symbol(symbol: str, timeframe: str = "1h", lookback: int = 1000,
                            atr_period: int = ATR_PERIOD, tp_mult: float = TP_ATR_MULT, sl_mult: float = SL_ATR_MULT,
                            position_usd: float = POSITION_USD) -> Dict[str,Any]:
    """
    Simple backtest: run through OHLCV series, if 1h price change > threshold open long/short,
    TP/SL by ATR. This is a simplified event-driven sim (no slippage by default, but we will include slippage & fee factors).
    Returns metrics (win_rate, pf, sharpe, trades, balance_curve).
    """
    ohlcv = fetch_ohlcv(symbol, timeframe=timeframe, limit=lookback+50)
    if not ohlcv or len(ohlcv) < 50:
        return {"error":"no_ohlcv"}
    # convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"])
    df["ts"] = pd.to_datetime(df["ts"], unit='ms', utc=True).dt.tz_convert(JST)
    # compute ATR
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    trs = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
    atrs = pd.Series(np.concatenate([np.zeros(1), trs])).rolling(atr_period).mean().fillna(method="bfill").values

    balance = 10000.0
    balance_curve = []
    trades = []

    fee_rate = float(os.getenv("BACKTEST_FEE_RATE", "0.0005"))  # 0.05% per side
    slippage = float(os.getenv("BACKTEST_SLIPPAGE", "0.0005"))

    for i in range(atr_period+1, len(df)-1):
        close_now = float(df["close"].iloc[i])
        close_prev = float(df["close"].iloc[i-1])
        pct_change = (close_now / close_prev - 1.0) * 100.0
        atr = float(atrs[i])
        # signal rules: momentum
        entry_side = None
        if pct_change > float(os.getenv("BACKTEST_ENTRY_PCT", "5.0")):
            entry_side = "long"
        elif pct_change < -float(os.getenv("BACKTEST_ENTRY_PCT", "5.0")):
            entry_side = "short"
        if entry_side:
            entry_price = close_now * (1 + slippage if entry_side=="long" else 1 - slippage)
            tp = entry_price + (tp_mult * atr if entry_side=="long" else -tp_mult * atr)
            sl = entry_price - (sl_mult * atr if entry_side=="long" else -sl_mult * atr)
            # simulate until TP/SL or max horizon 48 bars
            exit_price = None
            exit_index = None
            reason = "HOLD"
            for j in range(i+1, min(len(df), i+48)):
                high = float(df["high"].iloc[j])
                low = float(df["low"].iloc[j])
                if entry_side == "long":
                    # TP
                    if high >= tp:
                        exit_price = tp * (1 - slippage)
                        exit_index = j
                        reason = "TP"
                        break
                    if low <= sl:
                        exit_price = sl * (1 + slippage)
                        exit_index = j
                        reason = "SL"
                        break
                else:
                    if low <= tp:
                        exit_price = tp * (1 + slippage)
                        exit_index = j
                        reason = "TP"
                        break
                    if high >= sl:
                        exit_price = sl * (1 - slippage)
                        exit_index = j
                        reason = "SL"
                        break
            if exit_price is None:
                # exit at next bar close
                exit_price = float(df["close"].iloc[min(i+1, len(df)-1)])
                reason = "TIMEOUT"
            # compute pnl per contract: for linear futures, amount = USD / entry_price
            amount = position_usd / entry_price
            if entry_side == "long":
                pnl = (exit_price - entry_price) * amount
            else:
                pnl = (entry_price - exit_price) * amount
            # subtract fees both sides
            fees = (entry_price * amount + exit_price * amount) * fee_rate
            pnl_net = pnl - fees
            balance += pnl_net
            trades.append({"symbol": symbol, "side": entry_side, "entry": entry_price, "exit": exit_price, "pnl": pnl_net, "reason": reason})
            balance_curve.append(balance)
            # move i to exit_index roughly to avoid overlapping signals (conservative)
            if exit_index:
                i = exit_index
    # metrics
    pnls = np.array([t["pnl"] for t in trades]) if trades else np.array([])
    win_rate = float((pnls > 0).sum()) / len(pnls) * 100 if pnls.size else 0.0
    gross_profit = pnls[pnls>0].sum() if pnls.size else 0.0
    gross_loss = -pnls[pnls<0].sum() if pnls.size else 0.0
    pf = (gross_profit / gross_loss) if gross_loss>0 else float("inf") if gross_profit>0 else 0.0
    sharpe = (pnls.mean() / (pnls.std()+1e-9) * np.sqrt(252)) if pnls.size>1 else 0.0
    dd = 0.0
    if balance_curve:
        arr = np.array(balance_curve)
        peak = np.maximum.accumulate(arr)
        dd = float(((arr - peak)/peak).min() * 100)
    return {
        "symbol": symbol,
        "trades": trades,
        "balance_curve": balance_curve,
        "win_rate": win_rate,
        "profit_factor": pf,
        "sharpe": sharpe,
        "max_drawdown_pct": dd,
        "n_trades": len(trades)
    }

# --------------- Main trading cycle ----------------
def run_cycle():
    logging.info("=== cycle start === %s", utcnow_jst_iso())
    fg = fetch_fear_and_greed()
    top_symbols = fetch_top_symbols(MONITORED_TOP_N)
    snapshot = {"timestamp": utcnow_jst_iso(), "symbols": {}}

    # Run backtester for each symbol (but lightweight: maybe limit or cache in prod)
    backtest_cache = {}
    for sym in top_symbols:
        try:
            bt = run_backtest_for_symbol(sym, timeframe="1h", lookback=1000)
            backtest_cache[sym] = bt
        except Exception as e:
            backtest_cache[sym] = {"error": str(e)}

    for sym in top_symbols:
        try:
            price = None
            try:
                ticker = ccxt_client.fetch_ticker(symbol_market_ccxt(sym))
                price = ticker.get("last") or ticker.get("close")
            except Exception:
                # fallback to OHLCV last close
                o = fetch_ohlcv(sym, timeframe="1m", limit=2)
                if o:
                    price = o[-1][4]
            if price is None:
                logging.debug("%s price missing", sym)
                continue

            ohlcv_m = fetch_ohlcv(sym, timeframe="1m", limit=200)
            atr = calc_atr_from_ohlcv(fetch_ohlcv(sym, timeframe="1d", limit=ATR_PERIOD+5), period=ATR_PERIOD)
            ob = fetch_orderbook(sym, depth=50)
            comment, score = generate_ai_comment(sym, price, atr, ob, fg, ohlcv_m)
            snapshot["symbols"][sym] = {"price": price, "atr": atr, "orderbook": {"bid_vol": ob["bid_vol"], "ask_vol": ob["ask_vol"]}, "score": score, "ai": comment}
            # Decision logic: use score & backtest filter
            bt = backtest_cache.get(sym, {})
            pass_filter = True
            # Example filter: require bt n_trades>=20 and win_rate>40 and sharpe>0.5
            if isinstance(bt, dict) and bt.get("n_trades", 0) >= 20:
                if bt.get("win_rate", 0) < 40 or bt.get("sharpe", 0) < 0.2:
                    pass_filter = False
            # Signal rule: if score>60 and recent 1m momentum positive -> LONG, if score<40 negative -> SHORT
            # compute 1m momentum
            signal = None
            if len(ohlcv_m) >= 2:
                last = ohlcv_m[-1][4]
                prev = ohlcv_m[-2][4]
                pct = (last/prev -1.0) * 100
                if score >= 60 and pct > 0.2 and pass_filter:
                    signal = "long"
                elif score <= 40 and pct < -0.2 and pass_filter:
                    signal = "short"
            # Execute simulated entry (paper) or live if configured
            if signal and not state.has_position(sym):
                tp = last + TP_ATR_MULT * atr if signal == "long" else last - TP_ATR_MULT * atr
                sl = last - SL_ATR_MULT * atr if signal == "long" else last + SL_ATR_MULT * atr
                size_usd = POSITION_USD
                # check balance & sizing
                balance = state.get_balance()
                if size_usd > balance * 0.2:
                    # don't allocate more than 20% of balance
                    size_usd = balance * 0.2
                # run backtester quick check: if bt shows PF>1 prefer entry
                if bt and isinstance(bt, dict) and bt.get("profit_factor", 0) > 0:
                    bt_pf = bt.get("profit_factor", 0)
                    if bt_pf < 0.5:
                        logging.info("Skipping %s due to weak backtest pf=%.2f", sym, bt_pf)
                        continue
                # open position via executor
                leverage = dynamic_leverage(balance, atr, last)
                res = executor.open_position(sym, signal, size_usd, last, tp, sl, leverage=leverage)

                # send telegram
                msg = f"<b>📥 新規ポジション {'(SIM)' if res.get('simulated') else ''}</b>\n"
                msg += f"<b>{sym}</b> {signal.upper()} @ <code>{last:.6f}</code>\n"
                msg += f"Size(USDT): <code>{size_usd:.2f}</code>  Size(asset): <code>{res.get('amount', 0):.6f}</code>\n"
                msg += f"TP: <code>{tp:.6f}</code>  SL: <code>{sl:.6f}</code>\n"
                msg += "<pre>" + comment + "</pre>"
                send_telegram_html(msg)
        except Exception as e:
            logging.exception("symbol processing failed %s: %s", sym, e)
        time.sleep(0.05)

    # persist snapshot
    balance = executor.exchange.fetch_balance({'type': 'future'})
    positions = executor.exchange.fetch_positions()
    state.update_last_snapshot(snapshot, balance, positions)
    logging.info("=== cycle finished === %s", utcnow_jst_iso())

# ---------------- position checker for TP/SL (runs each minute) ----------------
def check_positions_and_manage():
    logging.info("=== check positions ===")
    positions = state.get_positions()
    for sym, pos in list(positions.items()):
        try:
            price = None
            try:
                t = ccxt_client.fetch_ticker(symbol_market_ccxt(sym))
                price = t.get("last") or t.get("close")
            except Exception:
                o = fetch_ohlcv(sym, timeframe="1m", limit=2)
                if o:
                    price = o[-1][4]
            if price is None:
                continue
            side = pos["side"]
            tp = float(pos["take_profit"])
            sl = float(pos["stop_loss"])
            # handle multi-step partial closes: for simplicity close full when reach TP/SL
            if side == "long":
                if price >= tp:
                    rec = executor.close_position(sym, portion=1.0)
                    msg = f"<b>✅ TP executed</b>\n<b>{sym}</b>\nExit: <code>{price:.6f}</code>\nPnL: <code>{rec.get('pnl',0):.4f}</code>"
                    send_telegram_html(msg)
            else:
                if price <= tp:
                    rec = executor.close_position(sym, portion=1.0)
                    msg = f"<b>✅ TP executed</b>\n<b>{sym}</b>\nExit: <code>{price:.6f}</code>\nPnL: <code>{rec.get('pnl',0):.4f}</code>"
                    send_telegram_html(msg)
            # stoploss
            if side == "long" and price <= sl:
                rec = executor.close_position(sym, portion=1.0)
                msg = f"<b>❌ SL executed</b>\n<b>{sym}</b>\nExit: <code>{price:.6f}</code>\nPnL: <code>{rec.get('pnl',0):.4f}</code>"
                send_telegram_html(msg)
            if side == "short" and price >= sl:
                rec = executor.close_position(sym, portion=1.0)
                msg = f"<b>❌ SL executed</b>\n<b>{sym}</b>\nExit: <code>{price:.6f}</code>\nPnL: <code>{rec.get('pnl',0):.4f}</code>"
                send_telegram_html(msg)
        except Exception as e:
            logging.exception("check pos failed %s: %s", sym, e)

# ---------------- Scheduler & Flask status ----------------
@app.route("/health")
def health():
    return "ok", 200

@app.route("/status")
def status():
    key = request.args.get("key", "")
    if key != STATUS_KEY:
        return jsonify({"error": "unauthorized"}), 401
    snap = state.get_state_snapshot()
    snap["server_time_jst"] = utcnow_jst_iso()
    snap["paper_trading"] = PAPER_TRADING
    snap["monitored"] = fetch_top_symbols(MONITORED_TOP_N)
    snap["telegram_configured"] = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
    snap["executor_ok"] = (executor.exchange is not None)
    return jsonify(snap)

def start_scheduler():
    # trading cycle every 1 minute
    schedule.every(1).minutes.do(run_cycle)
    # check positions every 1 minute
    schedule.every(1).minutes.do(check_positions_and_manage)
    # hourly report at JST minute==0
    while True:
        schedule.run_pending()
        time.sleep(1)

def test_force_order():
    """強制的に1回テスト注文を出す"""
    symbol = "BTCUSDT"   # テストする銘柄
    side = "buy"         # "buy" or "sell"
    price = 27000        # 想定価格（現値近辺にする）
    leverage = 5

    try:
        order = state.execute_entry(
            ccxt_client, symbol, side, price, leverage=leverage, risk_pct=1.0
        )
        logging.info(f"[TEST] 強制注文発注結果: {order}")
    except Exception as e:
        logging.error(f"[TEST] 強制注文失敗: {e}")

if __name__ == "__main__":
    logging.info("Starting Trend Sentinel (Bitget Futures). PAPER_TRADING=%s", PAPER_TRADING)
    t = threading.Thread(target=start_scheduler, daemon=True)
    t.start()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)











