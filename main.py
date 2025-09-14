# main.py
import os
import threading
import time
import logging
import asyncio
import atexit
from flask import Flask
import pandas as pd

# --- 1. モジュールと設定をインポート ---
import config
from state_manager import StateManager
from data_aggregator import DataAggregator
from trading_executor import TradingExecutor
from scoring_engine import ScoringEngine
from analysis_engine import AnalysisEngine
from telegram_notifier import TelegramNotifier
import risk_filter

# --- 2. ログと各クラスのインスタンス化 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
state = StateManager()
data_agg = DataAggregator()
trader = TradingExecutor(state)
scorer = ScoringEngine(trader.exchange)
analyzer = AnalysisEngine()
notifier = TelegramNotifier()
app = Flask(__name__)

# --- 3. 永続化とWebサーバー機能 ---
# プログラム終了時に状態をファイルに保存する処理を登録
atexit.register(state.save_state_to_disk)

@app.route('/')
def health_check():
    """RenderのヘルスチェックやUptimeRobotからのアクセスに応答する"""
    bot_status = 'ACTIVE' if config.IS_BOT_ACTIVE else 'INACTIVE'
    position_count = len(state.get_all_active_positions())
    return f"✅ Auto Trading Bot is {bot_status}. Active Positions: {position_count}"

# --- 4. 非同期対応の分析・取引ロジック ---
async def analyze_candidate_async(candidate, signal_type, fng_data, time_frame):
    """非同期で単一の候補を分析するコルーチン（動的タイムフレーム対応）"""
    yf_ticker = f"{candidate['symbol'].upper()}-USD"
    
    loop = asyncio.get_event_loop()
    # yfinanceの同期的な呼び出しを、非同期コードをブロックしないようにスレッドプールで実行
    series = await loop.run_in_executor(None, data_agg.fetch_ohlcv, yf_ticker, time_frame['period'], time_frame['interval'])
    if series.empty:
        return None
    
    score, analysis, regime = scorer.generate_score_and_analysis(candidate, series, fng_data, signal_type)
    entry_threshold = config.ENTRY_SCORE_THRESHOLD_TRENDING if regime == 'TRENDING' else config.ENTRY_SCORE_THRESHOLD_RANGING
    
    if score >= entry_threshold:
        return {'type': signal_type, 'token': candidate, 'series': series, 'score': score, 'analysis': analysis}
    elif score >= entry_threshold * 0.7:
        # スコアが閾値に近ければ、次の機会のためにウォッチリストに追加
        state.update_watchlist(candidate['id'], score)
    
    return None

async def run_trading_cycle_async():
    """非同期で実行されるメインの取引サイクル"""
    if not config.IS_BOT_ACTIVE:
        logging.warning("BOT is INACTIVE. Skipping cycle.")
        return
        
    logging.info("--- 🚀 Starting New Intelligent Trading Cycle ---")

    # フェーズ1: 既存ポジションの監視とBOTの自己評価
    trader.check_active_positions(data_agg, notifier=notifier)
    win_rate = state.get_win_rate()
    logging.info(f"Current Bot Win Rate: {win_rate:.2f}%")

    # フェーズ2: ポートフォリオのリスク管理
    if len(state.get_all_active_positions()) >= config.MAX_OPEN_POSITIONS:
        logging.warning(f"Max positions ({config.MAX_OPEN_POSITIONS}) reached. Skipping new signal generation.")
        return

    # フェーズ3: 市場状況把握と分析戦略の決定
    fng_data, _ = data_agg.get_fear_and_greed_index()
    btc_series_daily = data_agg.fetch_ohlcv(config.MARKET_CONTEXT_TICKER, '90d', '1d')
    if btc_series_daily.empty:
        logging.error("Could not fetch BTC data for market context. Aborting cycle.")
        return
    
    btc_series_daily.ta.atr(append=True)
    volatility = btc_series_daily['ATRp_14'].iloc[-1]
    if volatility > 4.0:
        time_frame = {'period': '7d', 'interval': '1h'}
        logging.info(f"High volatility detected (BTC ATRp: {volatility:.2f}%). Using SHORT-TERM (1h) analysis.")
    else:
        time_frame = {'period': '60d', 'interval': '4h'}
        logging.info(f"Low volatility detected (BTC ATRp: {volatility:.2f}%). Using MID-TERM (4h) analysis.")

    # フェーズ4: 分析候補のリストアップ
    all_data = data_agg.get_all_chains_data()
    if all_data.empty: return
    safe_data = risk_filter.filter_risky_tokens(all_data)
    long_df, short_df, _, _ = analyzer.run_analysis(safe_data)
    
    candidates_map = {}
    def add_candidate(token, signal_type):
        candidates_map.setdefault(token['id'], {'token': token, 'signals': set()})['signals'].add(signal_type)

    watchlist_ids = state.get_watchlist().keys()
    for _, token in safe_data[safe_data['id'].isin(watchlist_ids)].iterrows():
        add_candidate(token, 'LONG' if token['price_change_24h'] > 0 else 'SHORT')
    for _, token in long_df.head(config.CANDIDATE_POOL_SIZE).iterrows(): add_candidate(token, 'LONG')
    for _, token in short_df.head(config.CANDIDATE_POOL_SIZE).iterrows(): add_candidate(token, 'SHORT')

    # フェーズ5: 非同期での並列分析
    tasks = [analyze_candidate_async(data['token'], stype, fng_data, time_frame) for data in candidates_map.values() for stype in data['signals']]
    if tasks:
        logging.info(f"Analyzing {len(tasks)} potential signals concurrently...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = [r for r in results if r is not None and not isinstance(r, Exception)]
        if valid_results:
            best_trade_candidate = max(valid_results, key=lambda x: x['score'])
            trade = best_trade_candidate
            logging.info(f"HIGH-CONFIDENCE SIGNAL found: {trade['token']['symbol'].upper()} ({trade['type']}), Score: {trade['score']:.1f}")
            
            # 勝率に応じて最大取引額を調整
            adjusted_max_size = config.MAX_POSITION_SIZE_USD * (win_rate / 100) if win_rate > 50 else config.BASE_POSITION_SIZE_USD
            position_size = trader.calculate_position_size(config.BASE_POSITION_SIZE_USD, adjusted_max_size, trade['score'])
            
            trader.open_position(
                trade['type'], trade['token']['id'], trade['series'], trade['score'],
                notifier=notifier, analysis_comment=trade['analysis'], position_size_usd=position_size
            )
        else:
            logging.info("No high-confidence trading opportunities found.")

    logging.info("--- ✅ Intelligent Trading Cycle Finished ---")

# --- 5. スケジューラとプログラム起動 ---
def run_scheduler():
    """スケジュールを管理し、非同期タスクを呼び出す"""
    logging.info("Scheduler started.")
    
    async def periodic_task():
        # 6時間ごとに取引サイクルを実行するタスク
        # TODO: config.pyのスケジュール設定を読み込むように改良
        while True:
            await run_trading_cycle_async()
            state.save_state_to_disk() # サイクルごとに状態を保存
            await asyncio.sleep(6 * 3600) # 6時間待機

    # メインの非同期ループを開始
    asyncio.run(periodic_task())

if __name__ == "__main__":
    logging.info("Initializing Bot...")
    # BOTのメインロジックを開始する前に、状態をファイルから読み込む
    state.load_state_from_disk()
    
    # BOTのメインロジック(スケジューラ)をバックグラウンドスレッドで実行
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    # Webサーバーをメインスレッドで実行
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
