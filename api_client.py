import asyncio
import aiohttp
import logging
import random
import os
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
            logging.info(f"Successfully fetched data for {chain} via proxy.")
            return data.get('pairs', [])
    except Exception as e:
        logging.error(f"DEX Screener API failed for {chain}: {e}.")
        return []

async def fetch_ohlcv_data(session, chain_id, pair_address):
    if not chain_id or not pair_address: return []
    url = f"https://api.dexscreener.com/latest/dex/ohlcv/pairs/{pair_address}?res=60&limit=24"
    proxy = PROXY_URL if PROXY_URL else None
    try:
        async with session.get(url, timeout=15, proxy=proxy) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('ohlcv', [])
    except Exception as e:
        logging.warning(f"Failed to fetch OHLCV data for {pair_address} on {chain_id}: {e}")
        return []

async def fetch_moralis_data(session, chain_name, token_address):
    """Moralis APIからオンチェーンデータを取得する（堅牢性を向上）"""
    if not MORALIS_API_KEY:
        return {"holder_change_24h": 0}
    
    chain_map = {"ethereum": "eth", "bsc": "bsc", "polygon": "polygon", "avalanche": "avalanche", 
                 "arbitrum": "arbitrum", "optimism": "optimism", "base": "base", "solana": "sol"}
    moralis_chain = chain_map.get(chain_name)
    if not moralis_chain:
        return {"holder_change_24h": 0}

    url = f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/holders"
    headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
    
    try:
        async with session.get(url, headers=headers, proxy=PROXY_URL) as response:
            response.raise_for_status()
            data = await response.json()
            
            # ✅ 修正点: 安全なデータアクセス
            summary = data.get('summary', {})
            if summary: # summaryがNoneでないことを確認
                holders_change = summary.get('holders_change_24h', {})
                if holders_change: # holders_changeがNoneでないことを確認
                    change_percent = holders_change.get('percent', 0)
                    return {"holder_change_24h": change_percent or 0} # change_percentがNoneの場合も0を返す
            
            return {"holder_change_24h": 0}

    except Exception as e:
        # エラーメッセージを具体的にログ出力
        logging.warning(f"Moralis API failed for {token_address} on {chain_name}: {e}")
        return {"holder_change_24h": 0}


async def fetch_social_data(session, token_symbol):
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}: {e}")
        return {"mentions": 0, "status": "unavailable"}

async def fetch_all_data_concurrently(target_pairs):
    """全データを並列取得するメイン関数"""
    async with aiohttp.ClientSession() as session:
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        all_pairs = [pair for result in market_results if result for pair in result]
        if not all_pairs:
            return []

        async def fetch_additional_data_for_pair(pair):
            """単一ペアの追加データをまとめて取得するヘルパー関数"""
            ohlcv_task = fetch_ohlcv_data(session, pair['chainId'], pair['pairAddress'])
            social_task = fetch_social_data(session, pair['baseToken']['symbol'])
            onchain_task = fetch_moralis_data(session, pair['chainId'], pair['baseToken']['address'])
            
            ohlcv_data, social_data, onchain_data = await asyncio.gather(ohlcv_task, social_task, onchain_task)
            
            pair['indicators'] = calculate_technical_indicators(ohlcv_data)
            pair['social_data'] = social_data
            pair['onchain_data'] = onchain_data
            return pair

        additional_data_tasks = [fetch_additional_data_for_pair(pair) for pair in all_pairs]
        updated_pairs = await asyncio.gather(*additional_data_tasks)
        
        final_pairs = [p for p in updated_pairs if p is not None]
        if len(final_pairs) != len(all_pairs):
            logging.warning("Some pairs were lost during the additional data fetching process.")
            
        return final_pairs
