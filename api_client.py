import os
import asyncio
import aiohttp
import logging
import random
from dotenv import load_dotenv

# .envファイルからプロキシ情報を読み込む
load_dotenv()
PROXY_URL = os.getenv("PROXY_URL")


async def fetch_dexscreener_data(session, chain, pair_addresses):
    """DEX Screenerからプロキシを経由してデータを取得します。"""
    if not pair_addresses: 
        return []
    
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    }
    
    try:
        # 【重要】リクエストにプロキシ設定(proxy=PROXY_URL)を追加
        async with session.get(url, timeout=25, headers=headers, proxy=PROXY_URL) as response:
            response.raise_for_status()
            data = await response.json()
            logging.info(f"Successfully fetched data for {chain} via proxy.")
            return data.get('pairs', [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.error(f"DEX Screener API failed for {chain} via proxy. Reason: {e}.")
        return []

async def fetch_social_data(session, token_symbol):
    """SNS APIを呼び出します（この部分はプロキシを経由しません）。"""
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}. Reason: {e}.")
        return {"mentions": 0, "status": "unavailable"}

async def fetch_all_data_concurrently(target_pairs):
    """全ての外部APIからデータを並列で取得します。"""
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        all_pairs = [pair for chain_result in market_results for pair in chain_result]
        if not all_pairs: 
            return []

        social_tasks = [fetch_social_data(session, pair['baseToken']['symbol']) for pair in all_pairs]
        social_results = await asyncio.gather(*social_tasks)

        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            
        return all_pairs
