import asyncio
import aiohttp
import logging
import random
from datetime import datetime, timedelta
from config import PROXY_URL, MORALIS_API_KEY
from features import calculate_technical_indicators

async def fetch_dexscreener_data(session, chain, pair_addresses):
    if not pair_addresses: return []
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    proxy = PROXY_URL if PROXY_URL else None
    try:
        async with session.get(url, timeout=20, proxy=proxy) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('pairs', [])
    except Exception as e:
        logging.error(f"DEX Screener API failed for {chain}: {e}.")
        return []

async def fetch_ohlcv_data(session, pair_address, timeframe='h1'):
    """指定された時間軸のOHLCVデータを取得する (h1: 1時間足, d1: 日足)"""
    if not pair_address: return []
    
    # 時間軸に応じてAPIの解像度パラメータ(res)を変更
    resolution_map = {'h1': '60', 'd1': '1D'}
    res = resolution_map.get(timeframe, '60')
    
    url = f"https://api.dexscreener.com/latest/dex/ohlcv/pairs/{pair_address}?res={res}&limit=30"
    proxy = PROXY_URL if PROXY_URL else None
    try:
        async with session.get(url, timeout=15, proxy=proxy) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('ohlcv', [])
    except Exception as e:
        logging.warning(f"Failed to fetch OHLCV data for {pair_address} ({timeframe}): {e}")
        return []

async def fetch_social_data(session, token_symbol):
    # (変更なし)
    pass

async def fetch_moralis_data(session, chain_name, token_address):
    # (変更なし)
    pass

async def fetch_all_data_concurrently(target_pairs):
    """全データを並列取得し、複数時間軸のテクニカル指標を追加する"""
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        all_pairs = [pair for result in market_results if result for pair in result]
        if not all_pairs: return []

        async def fetch_additional_data_for_pair(pair):
            """単一ペアの追加データをまとめて取得する"""
            # ✅ 修正点: 1時間足と日足のデータを両方取得
            ohlcv_h1_task = fetch_ohlcv_data(session, pair['pairAddress'], timeframe='h1')
            ohlcv_d1_task = fetch_ohlcv_data(session, pair['pairAddress'], timeframe='d1')
            social_task = fetch_social_data(session, pair['baseToken']['symbol'])
            onchain_task = fetch_moralis_data(session, pair['chainId'], pair['baseToken']['address'])
            
            ohlcv_h1, ohlcv_d1, social_data, onchain_data = await asyncio.gather(
                ohlcv_h1_task, ohlcv_d1_task, social_task, onchain_task
            )
            
            # ✅ 修正点: 両方のデータを渡してテクニカル指標を計算
            pair['indicators'] = calculate_technical_indicators(ohlcv_h1, ohlcv_d1)
            pair['social_data'] = social_data
            pair['onchain_data'] = onchain_data
            return pair

        additional_data_tasks = [fetch_additional_data_for_pair(pair) for pair in all_pairs]
        updated_pairs = await asyncio.gather(*additional_data_tasks)
        
        return [p for p in updated_pairs if p is not None]

