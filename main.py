# main.py
import os
import logging
import asyncio
import schedule
import time
from threading import Thread
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# load dotenv if you use .env locally
from dotenv import load_dotenv
load_dotenv()

# --- import project modules (assumed present in backend/) ---
import config
from state_manager import StateManager
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
from trading_executor import TradingExecutor
from telegram_notifier import TelegramNotifier

# ------------------------------------------------------------
# logger
# ------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ------------------------------------------------------------
# init core objects
# ------------------------------------------------------------
state = StateManager(filename=config.STATE_FILE)
data_agg = DataAggregator()       # should initialize ccxt.bitget client inside
analyzer = AnalysisEngine()
trader = TradingExecutor(state)   # trading_executor created earlier; we'll toggle exchange.options['defaultType']
notifier = TelegramNotifier()

# ------------------------------------------------------------
# Helpers: AI-like comment generator + TP/SL calculator
# ------------------------------------------------------------
def compute_atr_like(series: pd.DataFrame, length: int = 14) -> float:
    """簡易ATR: 14期間の平均True Range。 series must have 'high','low','close'."""
    try:
        h = series['high']; l = series['low']; c = series['close']
        prev_c = c.shift(1).fillna(c.iloc[0])
        tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        atr = tr.rolling(length, min_periods=1).mean().iloc[-1]
        return float(atr)
    except Exception as e:
        logging.debug("ATR compute failed: %s", e)
        return 0.0

def compute_market_risk_factors(fng_value: int, orderbook_summary: dict, series: pd.DataFrame):
    """複数の市場指標を正規化してリスクスコアを返す（0..1、値が低いほど安全）"""
    # fng: 0..100 (高いほど強気)
    fng_risk = max(0.0, min(1.0, (50 - (fng_value or 50)) / 50))  # FNGが低いと恐怖 -> リスク低く→逆張り? here treat lower FNG as cautious
    buy_ratio = orderbook_summary.get('buy_ratio', 50)
    ob_risk = 1.0 - (buy_ratio / 100.0)  # 買い優勢ならリスク低め
    # volatility: use ATR relative to price
    try:
        price = float(series['close'].iloc[-1])
        atr = compute_atr_like(series)
        vol_ratio = (atr / price) if price else 0.0
        vol_risk = max(0.0, min(1.0, vol_ratio * 20))  # scale
    except Exception:
        vol_risk = 0.5
    # weighted sum
    score = 0.4 * fng_risk + 0.3 * ob_risk + 0.3 * vol_risk
    return max(0.0, min(1.0, score))

def adaptive_tp_sl(entry_price: float, series: pd.DataFrame, orderbook_summary: dict, fng_value: int, balance_usd: float):
    """
    動的に TP / SL を計算するロジック
    - entry_price: 現在の価格
    - series: OHLCV dataframe (1m * 60)
    - orderbook_summary: buy_volume, sell_volume, buy_ratio
    - fng_value: Fear&Greed index int
    - balance_usd: アカウント残高
    戻り値: (take_profit_price, stop_loss_price, tp_pct, sl_pct)
    """
    # base ATR-derived distance
    atr = compute_atr_like(series)
    price = float(entry_price) if entry_price else (series['close'].iloc[-1] if not series.empty else None)
    if not price:
        # fallbacks
        tp_pct = 0.05
        sl_pct = 0.03
        return price * (1 + tp_pct), price * (1 - sl_pct), tp_pct, sl_pct

    # market risk
    risk_score = compute_market_risk_factors(fng_value, orderbook_summary, series)  # 0..1 (higher -> more risky)
    # higher risk -> tighter stop loss, larger take profit ratio (risk-on? or risk-off?)  
    # We'll target risk-reward ratio adjustment: if market volatile (risk high) then smaller SL, larger TP?
    # Use heuristic:
    base_tp = 0.05  # 5%
    base_sl = 0.03  # 3%
    # adjust using risk_score and balance
    # if risk_score high -> widen TP (capture big moves) but tighten SL proportionally to limit losses
    tp_pct = base_tp * (1 + risk_score * 1.5)   # up to ~ (1+1.5)=2.5x base
    sl_pct = base_sl * (1 - risk_score * 0.6)   # reduce SL when risk high (min 0.01)
    sl_pct = max(0.01, sl_pct)

    # orderbook bias: if buy_ratio >> 50 -> bullish bias -> for LONG slightly increase TP and tighten SL
    buy_ratio = orderbook_summary.get('buy_ratio', 50)
    bias = (buy_ratio - 50) / 100.0  # -0.5 .. +0.5
    tp_pct *= (1 + bias * 0.5)
    sl_pct *= (1 - bias * 0.3)

    # balance scaling: if balance small, be more conservative (smaller TP/SL)
    if balance_usd < 1000:
        tp_pct *= 0.9
        sl_pct *= 0.9
    elif balance_usd > 20000:
        tp_pct *= 1.1
        sl_pct *= 1.0

    take_profit_price = price * (1 + tp_pct)
    stop_loss_price = price * (1 - sl_pct)

    return round(float(take_profit_price), 8), round(float(stop_loss_price), 8), round(tp_pct, 4), round(sl_pct, 4)

def ai_commentary_for_token(series: pd.DataFrame, orderbook_summary: dict, fng_value: int):
    """
    簡易 AI コメント（ルールベース）：
    - トレンド（短期移動平均 vs 長期移動平均）
    - ボラティリティ（ATR）
    - 板の厚み（buy_ratio）
    - FNG コメント
    """
    try:
        closes = series['close']
        ma_short = closes.rolling(5, min_periods=1).mean().iloc[-1]
        ma_long = closes.rolling(30, min_periods=1).mean().iloc[-1]
        trend = "上昇トレンド" if ma_short > ma_long else "下降トレンド"
        atr = compute_atr_like(series)
        vol_comment = f"ATR={atr:.6f}"
        buy_ratio = orderbook_summary.get('buy_ratio', None)
        market_sent = f"FNG={fng_value}" if fng_value is not None else "FNG=N/A"
        ob_comment = f"板買い比率={buy_ratio}%" if buy_ratio is not None else "板情報N/A"
        comment = f"{trend} / {vol_comment} / {ob_comment} / {market_sent}"
        return comment
    except Exception as e:
        logging.debug("ai_comment error: %s", e)
        return "解析データ不足のためコメント生成不可"

# ------------------------------------------------------------
# Core cycle: generate candidates, compute TP/SL, notify, and execute orders
# ------------------------------------------------------------
async def run_trading_cycle_async():
    logging.info("=== Starting trading cycle ===")
    # 0) safety guard: is bot active?
    if not getattr(config, "IS_BOT_ACTIVE", True):
        logging.info("Bot is inactive, skipping cycle.")
        return

    # 1) Build watchlist: default BTC if no positions, else include positions' symbols + BTC for context
    positions = state.get_positions() or {}
    watch_symbols = ["BTC/USDT"] if not positions else ["BTC/USDT"] + list(positions.keys())
    logging.info("Watch symbols: %s", watch_symbols)

    # 2) fetch snapshot for each symbol (1m * 60)
    market_snapshot = data_agg.build_market_snapshot(watch_symbols)  # { symbol: { latest_price, history, orderbook } }
    fng = data_agg.fetch_fear_and_greed()
    fng_value = fng.get("value") if isinstance(fng, dict) else None

    # 3) Prepare universe summary for analysis_engine
    universe = []
    for sym in watch_symbols:
        info = market_snapshot.get(sym, {})
        hist = info.get("history", [])
        # convert history to DataFrame if present
        if hist:
            df = pd.DataFrame(hist, columns=['ts','close'])
            # can't compute 1h/24h from raw list of 60 1m closes only for 1h is good; 24h use ticker if available
            try:
                # reconstruct a dataframe with close, and try to fetch OHLCV full dataset for ATR etc.
                df_full = data_agg.fetch_price_ohlcv_ccxt(sym, timeframe="1m", limit=120)  # try 120 bars if available
            except Exception:
                df_full = None
        else:
            df_full = None

        # compute metrics used by AnalysisEngine: price_change_1h, price_change_24h (approx), volume change %
        # try to get 1h percent
        price_change_1h = 0.0
        if info.get("history"):
            try:
                last = info["history"][-1][1]
                first_1h = info["history"][0][1]  # 60 mins ago
                price_change_1h = (last / first_1h - 1) * 100 if first_1h else 0.0
            except Exception:
                price_change_1h = 0.0

        # 24h percent from exchange ticker if available
        price_change_24h = 0.0
        try:
            ticker = data_agg.ex.fetch_ticker(sym)
            price_change_24h = float(ticker.get('percentage') or 0.0)
        except Exception:
            price_change_24h = 0.0

        # approximate volume percent using last bucket volumes (if history included volumes)
        # here info.history may not include volume; use fetch_price_ohlcv_ccxt to get volume
        vol_pct = 0.0
        try:
            df_v = data_agg.fetch_price_ohlcv_ccxt(sym, timeframe="1m", limit=120)
            if not df_v.empty:
                # compare last 60' total vol vs previous 60'
                last60 = df_v['volume'].tail(60).sum()
                prev60 = df_v['volume'].head(60).sum() if len(df_v) >= 120 else df_v['volume'].head(30).sum()
                vol_pct = ((last60 / prev60) - 1) * 100 if prev60 > 0 else 0.0
        except Exception:
            vol_pct = 0.0

        universe.append({
            "symbol": sym,
            "price_change_1h": price_change_1h,
            "price_change_24h": price_change_24h,
            "volume_change_24h": vol_pct,
            "series": df_full if isinstance(df_full, pd.DataFrame) else pd.DataFrame(),
            "orderbook": info.get("orderbook", {})
        })

    # 4) Run analysis engine to get candidates
    long_candidates, short_candidates, spike_candidates = analyzer.analyze_universe(universe)

    # 5) Build notification message header
    now_jst = datetime.now(timezone.utc).astimezone().strftime("%Y/%m/%d %H:%M JST")
    header = f"📡 トレンドセンチネル速報（{now_jst}）\n"
    header += f"監視銘柄数: {len(universe)}  / 保有ポジション: {len(positions)}\n\n"

    body_lines = []
    # helper to format one candidate
    def format_candidate(cand):
        sym = cand['symbol']
        # find source info
        info = next((u for u in universe if u['symbol'] == sym), None)
        series = info['series'] if info else pd.DataFrame()
        orderbook = info['orderbook'] if info else {}
        price = info['series']['close'].iloc[-1] if (info and not series.empty) else (market_snapshot.get(sym,{}).get('latest_price'))
        fng_val = fng_value
        balance = state.get_balance()
        tp, sl, tp_pct, sl_pct = adaptive_tp_sl(price, series if not series.empty else pd.DataFrame({'close':[price]}), orderbook, fng_val, balance)
        comment = ai_commentary_for_token(series if not series.empty else pd.DataFrame({'close':[price]}), orderbook, fng_val)
        line = {
            "symbol": sym,
            "price": price,
            "24h": cand.get("24h", cand.get("price_change_24h", 0.0)),
            "1h": cand.get("1h", cand.get("price_change_1h", 0.0)),
            "vol_pct": cand.get("vol_pct", cand.get("volume_change_24h", 0.0)),
            "tp": tp,
            "sl": sl,
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "comment": comment,
            "orderbook": orderbook
        }
        return line

    # 6) Prepare LONG message
    long_lines = [format_candidate(c) for c in long_candidates]
    if long_lines:
        body_lines.append("✅ LONG 候補（現物でロングを検討）:\n")
        for l in long_lines[:config.MAX_PER_NOTIFICATION if hasattr(config,'MAX_PER_NOTIFICATION') else 10]:
            body_lines.append(f"- {l['symbol']} 価格:{l['price']:.4f} 24h:{l['24h']:+.2f}% 1h:{l['1h']:+.2f}% Vol:{l['vol_pct']:+.0f}%")
            body_lines.append(f"  利確:{l['tp']:.4f} (+{l['tp_pct']*100:.2f}%) 損切:{l['sl']:.4f} (-{l['sl_pct']*100:.2f}%)")
            body_lines.append(f"  注釈: {l['comment']}")
            body_lines.append("")

    # 7) Prepare SHORT message (先物でショート)
    short_lines = [format_candidate(c) for c in short_candidates]
    if short_lines:
        body_lines.append("⚠️ SHORT 候補（先物でショートを検討）:\n")
        for l in short_lines[:config.MAX_PER_NOTIFICATION if hasattr(config,'MAX_PER_NOTIFICATION') else 10]:
            body_lines.append(f"- {l['symbol']} 価格:{l['price']:.4f} 24h:{l['24h']:+.2f}% 1h:{l['1h']:+.2f}% Vol:{l['vol_pct']:+.0f}%")
            body_lines.append(f"  利確:{l['tp']:.4f} (+{l['tp_pct']*100:.2f}%) 損切:{l['sl']:.4f} (-{l['sl_pct']*100:.2f}%)")
            body_lines.append(f"  注釈: {l['comment']}")
            body_lines.append("")

    # 8) Spikes
    if spike_candidates:
        body_lines.append("⚡ 急騰アラート:\n")
        for s in spike_candidates[:config.MAX_PER_NOTIFICATION if hasattr(config,'MAX_PER_NOTIFICATION') else 10]:
            body_lines.append(f"- {s['symbol']} 1h:{s.get('1h',0):+.2f}% vol:{s.get('vol_pct',0):+.0f}%")
        body_lines.append("")

    # 9) Send candidate notification
    message = header + "\n".join(body_lines)
    notifier.send(message)

    # 10) Automatic execution policy:
    #    - For each LONG candidate: open SPOT long (set exchange defaultType to spot)
    #    - For each SHORT candidate: open FUTURES short (set exchange defaultType to swap)
    #    - Respect MAX_OPEN_POSITIONS from config
    open_positions_count = len(state.get_positions() or {})
    max_allowed = getattr(config, "MAX_OPEN_POSITIONS", 5)
    spots_opened = 0
    futures_opened = 0

    # convenience: number of orders to place per cycle (configurable)
    max_new_per_cycle = getattr(config, "MAX_NEW_PER_CYCLE", 2)

    # function to execute and notify result
    def exec_and_notify(side, symbol, size_usd, tp, sl, comment, market_type):
        # toggle trader.exchange.options['defaultType'] if exchange exists
        try:
            if trader.exchange:
                trader.exchange.options['defaultType'] = 'spot' if market_type == 'spot' else 'swap'
        except Exception:
            pass

        # prepare 'series' param for trader.open_position signature if needed
        series_df = next((u['series'] for u in universe if u['symbol'] == symbol), pd.DataFrame())

        try:
            trader.open_position(side, symbol, series_df, score=85, notifier=notifier, analysis_comment=comment, position_size_usd=size_usd)
            # send success Telegram
            notifier.send(f"✅ 注文実行成功: {symbol} | {side} | size=${size_usd:.2f} | TP:{tp} SL:{sl}")
            return True
        except Exception as e:
            notifier.send(f"❌ 注文実行失敗: {symbol} | {side} | err: {e}")
            logging.exception("Order failed")
            return False

    # compute base size per position from state balance and conservative risk percentage
    balance = state.get_balance()
    # risk per trade 0.5% - 2% depending on balance
    if balance < 2000:
        risk_pct = 0.5 / 100.0
    elif balance < 20000:
        risk_pct = 1.0 / 100.0
    else:
        risk_pct = 1.5 / 100.0

    # process LONGs (spot)
    for l in long_lines:
        if open_positions_count >= max_allowed: break
        if spots_opened >= max_new_per_cycle: break
        symbol = l['symbol']
        # skip if already have position
        if state.get_positions().get(symbol): continue
        # size calculation: risk-based sizing using stop loss distance
        entry = l['price']
        tp = l['tp']; sl = l['sl']
        # estimate quantity via USD risk budget: risk_budget = balance * risk_pct
        # risk_per_unit = entry - sl
        risk_budget = max(1.0, balance * risk_pct)
        risk_per_unit = abs(entry - sl) if entry and sl else entry * 0.03
        size_in_asset = risk_budget / risk_per_unit if risk_per_unit > 0 else (risk_budget / entry)
        # convert to USD notional
        size_usd = min(risk_budget * 4, size_in_asset * entry)  # cap notional to 4x risk budget
        # execute spot buy (LONG)
        ok = exec_and_notify("LONG", symbol, size_usd, tp, sl, l['comment'], market_type='spot')
        if ok:
            spots_opened += 1
            open_positions_count += 1

    # process SHORTs (futures)
    for s in short_lines:
        if open_positions_count >= max_allowed: break
        if futures_opened >= max_new_per_cycle: break
        symbol = s['symbol']
        if state.get_positions().get(symbol): continue
        entry = s['price']
        tp = s['tp']; sl = s['sl']
        risk_budget = max(1.0, balance * risk_pct)
        risk_per_unit = abs(entry - sl) if entry and sl else entry * 0.03
        size_in_asset = risk_budget / risk_per_unit if risk_per_unit > 0 else (risk_budget / entry)
        size_usd = min(risk_budget * 4, size_in_asset * entry)
        ok = exec_and_notify("SHORT", symbol, size_usd, tp, sl, s['comment'], market_type='futures')
        if ok:
            futures_opened += 1
            open_positions_count += 1

    # 11) Save state at end of cycle
    state.save_state()
    logging.info("=== Trading cycle finished ===")

# ------------------------------------------------------------
# Scheduler thread
# ------------------------------------------------------------
def schedule_jobs():
    # schedule times in JST from config.TRADING_CYCLE_TIMES (strings "02:00", etc)
    for tstr in getattr(config, "TRADING_CYCLE_TIMES", ["02:00","08:00","14:00","20:00"]):
        schedule.every().day.at(tstr).do(lambda: asyncio.run(run_trading_cycle_async()))
        logging.info("Scheduled cycle at %s JST", tstr)
    # daily summary time
    daily_time = getattr(config, "DAILY_SUMMARY_TIME", "21:00")
    schedule.every().day.at(daily_time).do(lambda: asyncio.run(run_trading_cycle_async()))
    logging.info("Scheduled daily summary at %s JST", daily_time)

def run_scheduler_loop():
    schedule_jobs()
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error("Scheduler run_pending error: %s", e)
        time.sleep(1)

# ------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------
if __name__ == "__main__":
    logging.info("Initializing Trend Sentinel bot main...")
    # start scheduler thread (daemon)
    th = Thread(target=run_scheduler_loop, daemon=True)
    th.start()
    logging.info("Scheduler started (daemon thread). Bot is live.")

    # keep main process alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")
        state.save_state()
