import asyncio
import aiohttp
import logging
import random
import os

# PROXY_URLを環境変数から読み込む
PROXY_URL = os.getenv("PROXY_URL")

async def fetch_dexscreener_data(session, chain, pair_addresses):
    """DEX Screenerからデータを取得。プロキシを利用する。"""
    if not pair_addresses: 
        return []
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    
    # PROXY_URLが設定されていれば、proxy引数を使用
    proxy = PROXY_URL if PROXY_URL else None

    try:
        # proxy引数を追加
        async with session.get(url, timeout=20, proxy=proxy) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('pairs', [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.error(f"DEX Screener API failed for {chain}: {e}. Proceeding without it.")
        return []

async def fetch_social_data(session, token_symbol):
    """SNS APIを呼び出す（この部分はプロキシ不要な場合が多い）"""
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}. Reason: {e}. Proceeding without it.")
        return {"mentions": 0, "status": "unavailable"}

async def fetch_all_data_concurrently(target_pairs):
    """全データを並列取得"""
    # aiohttp.ClientSessionは一度だけ作成するのが効率的
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

        # sessionを再利用
        social_tasks = [fetch_social_data(session, pair['baseToken']['symbol']) for pair in all_pairs]
        social_results = await asyncio.gather(*social_tasks)

        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            
        return all_pairs
        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            

        return all_pairs
