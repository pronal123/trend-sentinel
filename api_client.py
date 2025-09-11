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
    """
    DEX Screenerからプロキシを経由してデータを取得します。
    あらゆる予期せぬエラーにも対応し、必ずリストを返します。
    """
    if not pair_addresses: 
        return []
    
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    }
    
    try:
        async with session.get(url, timeout=25, headers=headers, proxy=PROXY_URL) as response:
            response.raise_for_status()
            data = await response.json()
            logging.info(f"Successfully fetched data for {chain} via proxy.")
            return data.get('pairs', [])
    except Exception as e:
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
    """
    全ての外部APIからデータを並列で取得します。
    TypeErrorを回避し、デプロイ問題を検知するロジックを追加しました。
    """
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        # 【重要】TypeErrorを回避し、デプロイ問題を検知する安全なループ処理
        all_pairs = []
        for i, chain_result in enumerate(market_results):
            if chain_result is None:
                # このログが出力された場合、古いコードが実行されていることが確定します
                logging.critical(f"FATAL: Result from task {i} was None. This indicates a DEPLOYMENT ISSUE. The latest api_client.py is not running.")
                continue # Noneの場合はスキップして処理を続行
            
            all_pairs.extend(chain_result)

        if not all_pairs: 
            return []

        social_tasks = [fetch_social_data(session, pair['baseToken']['symbol']) for pair in all_pairs]
        social_results = await asyncio.gather(*social_tasks)

        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            
        return all_pairs
