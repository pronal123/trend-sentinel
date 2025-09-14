import os, logging, asyncio, schedule, time
from datetime import datetime, timezone
from threading import Thread

from config import TRADING_CYCLE_TIMES, DAILY_SUMMARY_TIME, MONITORED_CHAINS
from state_manager import StateManager
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
from telegram_notifier import TelegramNotifier
from trading_executor import TradingExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

state = StateManager()
data = DataAggregator()
analyzer = AnalysisEngine()
notifier = TelegramNotifier()
executor = TradingExecutor(state)

# helper: build token list to check: if have positions -> their symbols, else default BTC/USDT
def build_watch_symbols():
    pos = state.get_positions()
    if pos:
        return ["BTC/USDT"] + list(pos.keys())
    return ["BTC/USDT"]

async def perform_cycle():
    logging.info("=== Cycle start ===")
    symbols = build_watch_symbols()
    # 1) snapshot OHLCV (1m * 60) and orderbook; also fetch on-chain/social if integrated
    snapshot = data.build_market_snapshot(symbols)  # history + orderbook
    fng = data.fetch_fear_and_greed()
    # 2) derive metrics: 24h% & 1h% & vol pct & 15m mult
    market_summaries = []
    for s, info in snapshot.items():
        hist = info.get("history", [])
        # compute 1h% (last 60 points), 24h% maybe unavailable from 1m data -> we approximate or use external 24h price.
        prices = [p for ts,p in hist]
        if len(prices) < 2:
            continue
        last = prices[-1]
        # 1h % from 60min ago
        first_1h = prices[0]
        p1h = (last / first_1h - 1) * 100 if first_1h else 0
        # For 24h we attempt to fetch ticker 24h change using ccxt ticker
        try:
            ticker = data.ex.fetch_ticker(s)
            p24 = float(ticker.get('percentage') or 0)
        except Exception:
            p24 = 0.0
        # volume pct: compare last 24h volume vs previous (we don't have 24h in 1m window), fallback to 1m volume comparison:
        vol_recent = sum([0 if v is None else v for _,v in hist[-5:]])  # crude
        vol_prev = sum([0 if v is None else v for _,v in hist[:5]]) if len(hist)>=10 else vol_recent
        vol_pct = ((vol_recent / vol_prev) - 1) * 100 if vol_prev>0 else 0
        # 15m mult: ratio of last 15 to previous 15
        last15 = sum([p for p in prices[-15:]]) if len(prices) >= 15 else sum(prices)
        prev15 = sum([p for p in prices[-30:-15]]) if len(prices) >= 30 else last15
        vol15_mult = (last15 / prev15) if prev15>0 else 1.0

        market_summaries.append({
            "symbol": s,
            "24h": p24,
            "1h": p1h,
            "vol_pct": vol_pct,
            "vol_15m_mult": vol15_mult,
        })

    # 3) analyze
    longs, shorts, spikes = analyzer.analyze_universe(market_summaries)
    meta = {"total": len(market_summaries)}
    # 4) de-dup & spam control: skip if recently notified
    final_longs, final_shorts, final_spikes = [], [], []
    for t in longs:
        if not state.was_notified_recently(t['symbol']):
            final_longs.append(t)
            state.mark_notified(t['symbol'])
    for t in shorts:
        if not state.was_notified_recently(t['symbol']):
            final_shorts.append(t)
            state.mark_notified(t['symbol'])
    for t in spikes:
        if not state.was_notified_recently(t['symbol']):
            final_spikes.append(t)
            state.mark_notified(t['symbol'])

    # 5) prepare message & send
    notifier.send_trade_summary(final_longs, final_shorts, final_spikes, meta)

    # 6) optionally open positions (respect MAX_OPEN_POSITIONS and risk filters)
    # Here we open only top N long and short candidates (but real logic should include risk_filter)
    for cand in final_longs[:3]:
        score = 80  # placeholder
        size_usd = executor.calculate_position_size_usd(score)
        if size_usd>0:
            executor.open_position("LONG", cand["symbol"], size_usd, notifier=notifier)
    for cand in final_shorts[:3]:
        score = 80
        size_usd = executor.calculate_position_size_usd(score)
        if size_usd>0:
            executor.open_position("SHORT", cand["symbol"], size_usd, notifier=notifier)

    logging.info("=== Cycle finished ===")

# scheduler helpers
def schedule_jobs():
    # 6-hour cycles at TRADING_CYCLE_TIMES (strings like "02:00")
    for t in TRADING_CYCLE_TIMES:
        schedule.every().day.at(t).do(lambda: asyncio.run(perform_cycle()))
    # daily summary
    schedule.every().day.at(DAILY_SUMMARY_TIME).do(lambda: asyncio.run(send_daily_summary()))
    logging.info("Scheduled jobs set")

async def send_daily_summary():
    # Build concise daily summary from state.trade_history and maybe top movers
    wins = sum(1 for h in state.state.get("trade_history",[]) if h.get("result")=="win")
    losses = sum(1 for h in state.state.get("trade_history",[]) if h.get("result")=="loss")
    txt = f"📋 日次サマリー ({datetime.now().strftime('%Y/%m/%d')})\nトレード履歴: wins={wins} loss={losses}\n残高: {state.get_balance()} USD\n"
    notifier.send(txt)

def run_scheduler_loop():
    schedule_jobs()
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.info("Starting scheduler thread")
    t = Thread(target=run_scheduler_loop, daemon=True)
    t.start()
    # expose minimal web server for healthcheck/status if desired (left as extension)
    # keep main alive
    while True:
        time.sleep(60)
