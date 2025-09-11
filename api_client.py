import asyncio
import aiohttp
import logging
import random

# --- 各API呼び出し関数 ---

async def fetch_dexscreener_data(session, chain, pair_addresses):
    """DEX Screenerからデータを取得。エラー発生時も処理を継続。"""
    if not pair_addresses: 
        return []
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    try:
        async with session.get(url, timeout=15) as response:
            response.raise_for_status()
            data = await response.json()
            # 'pairs'キーが存在しない場合も安全に空リストを返す
            return data.get('pairs', [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logging.error(f"DEX Screener API failed for {chain}: {e}. Proceeding without it.")
        # 根本対策：エラー時は必ず空リストを返す
        return []

async def fetch_social_data(session, token_symbol):
    """Stocktwits/Reddit等のSNS APIを呼び出す。メンテナンス中でも停止しない。"""
    # NOTE: この関数は現在ダミーです。
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}. Reason: {e}. Proceeding without it.")
        return {"mentions": 0, "status": "unavailable"}

async def fetch_all_data_concurrently(target_pairs):
    """全データを並列取得。一部のAPIが失敗しても全体は停止しない。"""
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        # ✅ 追加の安全対策：万が一market_resultsにNoneが含まれても無視する
        all_pairs = [
            pair for chain_result in market_results 
            if chain_result is not None 
            for pair in chain_result
        ]
        
        if not all_pairs: 
            return []

        social_tasks = [fetch_social_data(session, pair['baseToken']['symbol']) for pair in all_pairs]
        social_results = await asyncio.gather(*social_tasks)

        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            
        return all_pairs