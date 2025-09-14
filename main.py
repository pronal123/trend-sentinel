# main.py
import os
import threading
import time
import logging
import asyncio
import atexit
import schedule
import pytz
from flask import Flask, render_template_string
import pandas as pd
import pandas_ta as ta

import config
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from analysis_engine import AnalysisEngine
from telegram_notifier import TelegramNotifier
import risk_filter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
analyzer = AnalysisEngine()
notifier = TelegramNotifier()
app = Flask(__name__)

atexit.register(state.save_state_to_disk)

@app.route('/')
def health_check():
    bot_status = 'ACTIVE' if config.IS_BOT_ACTIVE else 'INACTIVE'
    position_count = len(state.get_all_active_positions())
    return f"✅ Auto Trading Bot is {bot_status}. Active Positions: {position_count}"

STATUS_PAGE_HTML = """
<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="60">
... (HTML content) ...
"""

@app.route('/status')
def status_dashboard():
    total_balance = trader.get_account_balance_usd()
    fng_value, fng_sentiment = data_agg.get_fear_and_greed_index()
    btc_series = data_agg.fetch_ohlcv(config.MARKET_CONTEXT_TICKER, '90d', '1d')
    market_regime, analysis_comments = "N/A", "BTC data failed to load."
    if not btc_series.empty:
        btc_series.ta.atr(append=True)
        _, analysis_comments, market_regime = scorer.generate_score_and_analysis(
            {'symbol': 'BTC', 'id': 'bitcoin'}, btc_series, {'value': fng_value, 'sentiment': fng_sentiment}, 'LONG'
        )
    active_positions = state.get_all_active_positions()
    enriched_positions = []
    for token_id, details in active_positions.items():
        price = data_agg.get_latest_price(token_id)
        if price:
            details['current_price'] = price
            size = details.get('position_size', 0)
            pnl, pnl_percent = 0, 0
            if details.get('entry_price'):
                if details['side'] == 'long':
                    pnl = (price - details['entry_price']) * size
                    pnl_percent = (price / details['entry_price'] - 1) * 100 if details['entry_price'] else 0
                else:
                    pnl = (details['entry_price'] - price) * size
                    pnl_percent = (details['entry_price'] / price - 1) * 100 if price else 0
            details['pnl'], details['pnl_percent'] = pnl, pnl_percent
            enriched_positions.append(details)
    return render_template_string(STATUS_PAGE_HTML, positions=enriched_positions, total_balance=total_balance, market_regime=market_regime, fng_value=fng_value, fng_sentiment=fng_sentiment, analysis_comments=analysis_comments)

async def analyze_candidate_async(candidate, signal_type, fng_data, time_frame):
    yf_ticker = f"{candidate['symbol'].upper()}-USD"
    loop = asyncio.get_event_loop()
    series = await loop.run_in_executor(None, data_agg.fetch_ohlcv, yf_ticker, time_frame['period'], time_frame['interval'])
    if series.empty: return None
    score, analysis, regime = scorer.generate_score_and_analysis(candidate, series, fng_data, signal_type)
    entry_threshold = config.ENTRY_SCORE_THRESHOLD_TRENDING if regime == 'TRENDING' else config.ENTRY_SCORE_THRESHOLD_RANGING
    if score >= entry_threshold:
        return {'type': signal_type, 'token': candidate, 'series': series, 'score': score, 'analysis': analysis}
    elif score >= entry_threshold * 0.7:
        state.update_watchlist(candidate['id'], score)
    return None

async def run_trading_cycle_async():
    if not config.IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping cycle.")
        return
    logging.info("--- 🚀 Starting New Intelligent Trading Cycle ---")
    trader.check_active_positions(data_agg, notifier=notifier)
    win_rate = state.get_win_rate()
    logging.info(f"Current Bot Win Rate: {win_rate:.2f}%")
    if len(state.get_all_active_positions()) >= config.MAX_OPEN_POSITIONS:
        logging.warning(f"Max positions reached. Skipping new signal generation.")
        return
    fng_data, fng_sentiment = data_agg.get_fear_and_greed_index()
    btc_series_daily = data_agg.fetch_ohlcv(config.MARKET_CONTEXT_TICKER, '90d', '1d')
    if btc_series_daily.empty:
        logging.error("Could not fetch BTC data for market context. Aborting cycle.")
        return
    
    btc_series_daily.ta.atr(append=True) # THIS IS THE FIX
    
    volatility = btc_series_daily['ATRp_14'].iloc[-1]
    time_frame = {'period': '7d', 'interval': '1h'} if volatility > 4.0 else {'period': '60d', 'interval': '4h'}
    logging.info(f"Volatility detected (BTC ATRp: {volatility:.2f}%). Using {'SHORT' if volatility > 4.0 else 'MID'}-TERM analysis.")
    
    all_data = data_agg.get_all_chains_data()
    if all_data.empty: return
    safe_data = risk_filter.filter_risky_tokens(all_data)
    long_df, short_df, _, _ = analyzer.run_analysis(safe_data)
    
    candidates_map = {}
    def add_candidate(token, signal_type):
        candidates_map.setdefault(token['id'], {'token': token, 'signals': set()})['signals'].add(signal_type)

    watchlist_ids = state.get_watchlist().keys()
    for _, token in safe_data[safe_data['id'].isin(watchlist_ids)].iterrows():
        add_candidate(token.to_dict(), 'LONG' if token['price_change_24h'] > 0 else 'SHORT')
    for _, token in long_df.head(config.CANDIDATE_POOL_SIZE).iterrows(): add_candidate(token.to_dict(), 'LONG')
    for _, token in short_df.head(config.CANDIDATE_POOL_SIZE).iterrows(): add_candidate(token.to_dict(), 'SHORT')
    
    tasks = [analyze_candidate_async(data['token'], stype, {'value': fng_data, 'sentiment': fng_sentiment}, time_frame) for data in candidates_map.values() for stype in data['signals']]
    if tasks:
        logging.info(f"Analyzing {len(tasks)} potential signals concurrently...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = [r for r in results if r is not None and not isinstance(r, Exception)]
        if valid_results:
            best_trade_candidate = max(valid_results, key=lambda x: x['score'])
            trade = best_trade_candidate
            logging.info(f"HIGH-CONFIDENCE SIGNAL: {trade['token']['symbol'].upper()} ({trade['type']}), Score: {trade['score']:.1f}")
            adjusted_max_size = config.MAX_POSITION_SIZE_USD * (win_rate / 100) if win_rate > 50 else config.BASE_POSITION_SIZE_USD
            position_size = trader.calculate_position_size(trade['score'], base_size_usd=config.BASE_POSITION_SIZE_USD, max_size_usd=adjusted_max_size)
            trader.open_position(
                trade['type'], trade['token']['id'], trade['series'], trade['score'],
                notifier=notifier, analysis_comment=trade['analysis'], position_size_usd=position_size
            )
        else:
            logging.info("No high-confidence trading opportunities found.")
    logging.info("--- ✅ Intelligent Trading Cycle Finished ---")

def run_scheduler_sync():
    try:
        logging.info("Scheduler thread started.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for t in config.TRADING_CYCLE_TIMES:
            schedule.every().day.at(t, "Asia/Tokyo").do(lambda: loop.run_until_complete(run_trading_cycle_async_wrapper()))
        while True:
            schedule.run_pending()
            time.sleep(1)
    except Exception as e:
        logging.critical(f"Scheduler thread CRASHED: {e}", exc_info=True)

async def run_trading_cycle_async_wrapper():
    try:
        await run_trading_cycle_async()
    finally:
        state.save_state_to_disk()

logging.info("Initializing Bot...")
state.load_state_from_disk()
threading.Thread(target=run_scheduler_sync, daemon=True).start()

if __name__ == "__main__":
    logging.info("Starting Flask server for local testing...")
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
