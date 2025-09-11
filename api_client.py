# api_client.py (修正後のフルコード)
import asyncio
import aiohttp
import logging
import random
from datetime import datetime, timedelta
from config import PROXY_URL, MORALIS_API_KEY
from features import calculate_technical_indicators

# ... (fetch_dexscreener_data, fetch_ohlcv_data, fetch_social_data は変更なし) ...

async def fetch_moralis_data(session, chain_name, token_address):
    """Moralis APIからオンチェーンデータ（例: 保有者数の変化）を取得する"""
    if not MORALIS_API_KEY:
        return {"holder_change_24h": 0}
    
    # Moralisのチェーン名に変換 (例: bsc -> bsc, ethereum -> eth)
    chain_map = {"ethereum": "eth", "bsc": "bsc", "polygon": "polygon", "avalanche": "avalanche", 
                 "arbitrum": "arbitrum", "optimism": "optimism", "base": "base"}
    moralis_chain = chain_map.get(chain_name)
    if not moralis_chain:
        return {"holder_change_24h": 0}

    url = f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/holders?chain={moralis_chain}"
    headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
    
    try:
        async with session.get(url, headers=headers, proxy=PROXY_URL) as response:
            response.raise_for_status()
            data = await response.json()
            # 24hの保有者数変化率を取得 (APIレスポンスの例)
            change_24h = data.get('holderChange', {}).get('24h', {}).get('changePercent', 0)
            return {"holder_change_24h": change_24h}
    except Exception as e:
        logging.warning(f"Moralis API failed for {token_address} on {chain_name}: {e}")
        return {"holder_change_24h": 0}

async def fetch_all_data_concurrently(target_pairs):
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        all_pairs = [p for res in market_results if res for p in res]
        if not all_pairs: return []

        # ✅ 修正点: Moralisのタスクを呼び出す
        ohlcv_tasks = [fetch_ohlcv_data(session, p['chainId'], p['pairAddress']) for p in all_pairs]
        social_tasks = [fetch_social_data(session, p['baseToken']['symbol']) for p in all_pairs]
        onchain_tasks = [fetch_moralis_data(session, p['chainId'], p['baseToken']['address']) for p in all_pairs]
        
        ohlcv_results, social_results, onchain_results = await asyncio.gather(*ohlcv_tasks, *social_tasks, *onchain_tasks)

        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            pair['indicators'] = calculate_technical_indicators(ohlcv_results[i])
            pair['onchain_data'] = onchain_results[i]
            
        return all_pairs
