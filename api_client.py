import asyncio
import aiohttp
import logging
import random
import os

# プロジェクト内の他モジュールをインポート
from features import calculate_technical_indicators

# PROXY_URLを環境変数から読み込む
PROXY_URL = os.getenv("PROXY_URL")

async def fetch_dexscreener_data(session, chain, pair_addresses):
    """DEX Screenerから最新のペアデータを取得"""
    if not pair_addresses: 
        return []
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    proxy = PROXY_URL if PROXY_URL else None
    try:
        async with session.get(url, timeout=20, proxy=proxy) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('pairs', [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.error(f"DEX Screener API failed for {chain}: {e}. Proceeding without it.")
        return []

async def fetch_ohlcv_data(session, chain_id, pair_address):
    """
    DEX Screenerから特定のペアのOHLCVデータを取得する。
    ✅ チェーン名を動的に変更するよう修正。
    """
    if not chain_id or not pair_address:
        return []
        
    # 過去24時間分の1時間足データを取得 (RSI計算用)
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair_address}/ohlcv/h1?limit=24"
    proxy = PROXY_URL if PROXY_URL else None
    try:
        async with session.get(url, timeout=15, proxy=proxy) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('ohlcv', [])
    except Exception as e:
        logging.warning(f"Failed to fetch OHLCV data for {pair_address} on {chain_id}: {e}")
        return []

async def fetch_social_data(session, token_symbol):
    """SNS APIを呼び出す（ダミー）"""
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}: {e}")
        return {"mentions": 0, "status": "unavailable"}

async def fetch_all_data_concurrently(target_pairs):
    """全データを並列取得し、テクニカル指標を追加する"""
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        all_pairs = [
            pair for chain_result in market_results 
            if chain_result is not None 
            for pair in chain_result
        ]
        
        if not all_pairs: 
            return []

        # OHLCVデータとSNSデータの取得タスクを並列実行
        # ✅ 各ペアのチェーンID(pair['chainId'])とペアアドレス(pair['pairAddress'])を渡すよう修正
        ohlcv_tasks = [fetch_ohlcv_data(session, pair['chainId'], pair['pairAddress']) for pair in all_pairs]
        social_tasks = [fetch_social_data(session, pair['baseToken']['symbol']) for pair in all_pairs]
        
        ohlcv_results = await asyncio.gather(*ohlcv_tasks)
        social_results = await asyncio.gather(*social_tasks)

        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            pair['indicators'] = calculate_technical_indicators(ohlcv_results[i])
            
        return all_pairs
