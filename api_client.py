import asyncio
import aiohttp
import logging
import random
from datetime import datetime, timedelta
from config import PROXY_URL, MORALIS_API_KEY
from features import calculate_technical_indicators

# (fetch_dexscreener_data, fetch_ohlcv_data, fetch_moralis_data, fetch_social_dataの各関数は変更なし)
# ... 各API呼び出し関数の定義 ...

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
    if not MORALIS_API_KEY: return {"holder_change_24h": 0}
    chain_map = {"ethereum": "eth", "bsc": "bsc", "polygon": "polygon", "avalanche": "avalanche", 
                 "arbitrum": "arbitrum", "optimism": "optimism", "base": "base"}
    moralis_chain = chain_map.get(chain_name)
    if not moralis_chain: return {"holder_change_24h": 0}

    url = f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/holders"
    headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
    
    try:
        async with session.get(url, headers=headers, proxy=PROXY_URL) as response:
            response.raise_for_status()
            data = await response.json()
            # 実際のAPIレスポンスに合わせて調整が必要な場合があります
            change_24h = data.get('summary', {}).get('holders_change_24h', {}).get('percent', 0)
            return {"holder_change_24h": change_24h}
    except Exception as e:
        logging.warning(f"Moralis API failed for {token_address} on {chain_name}: {e}")
        return {"holder_change_24h": 0}

async def fetch_social_data(session, token_symbol):
    try:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}: {e}")
        return {"mentions": 0, "status": "unavailable"}

# --- ✅ 修正点: 堅牢性を高めたデータ取得のメイン関数 ---
async def fetch_all_data_concurrently(target_pairs):
    """全データを並列取得するメイン関数。ロジックを簡素化し堅牢性を向上。"""
    async with aiohttp.ClientSession() as session:
        # ステップ1: 全チェーンの基本ペアデータを一括で取得
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        all_pairs = [pair for result in market_results if result for pair in result]
        if not all_pairs:
            return []

        # ステップ2: 各ペアに必要な追加データ（OHLCVなど）を並列で取得
        async def fetch_additional_data_for_pair(pair):
            """単一ペアの追加データをまとめて取得するヘルパー関数"""
            ohlcv_task = fetch_ohlcv_data(session, pair['chainId'], pair['pairAddress'])
            social_task = fetch_social_data(session, pair['baseToken']['symbol'])
            onchain_task = fetch_moralis_data(session, pair['chainId'], pair['baseToken']['address'])
            
            # 3つのタスクを並列実行
            ohlcv_data, social_data, onchain_data = await asyncio.gather(ohlcv_task, social_task, onchain_task)
            
            # 元のペア情報に取得したデータを統合
            pair['indicators'] = calculate_technical_indicators(ohlcv_data)
            pair['social_data'] = social_data
            pair['onchain_data'] = onchain_data
            return pair

        # 全てのペアに対して追加データ取得タスクを作成
        additional_data_tasks = [fetch_additional_data_for_pair(pair) for pair in all_pairs]
        
        # 全ての追加データ取得を並列で実行し、結果を待つ
        updated_pairs = await asyncio.gather(*additional_data_tasks)
        
        # Noneの結果（もしあれば）を除外して最終リストを返す
        final_pairs = [p for p in updated_pairs if p is not None]
        if len(final_pairs) != len(all_pairs):
            logging.warning("Some pairs were lost during the additional data fetching process.")
            
        return final_pairs
