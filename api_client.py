import asyncio
import aiohttp
import logging
import random

# --- 各API呼び出し関数 ---

async def fetch_dexscreener_data(session, chain, pair_addresses):
    """
    DEX Screenerからデータを取得します。
    403エラーを回避するためUser-Agentヘッダーを追加しています。
    """
    if not pair_addresses: 
        return []
    
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{','.join(pair_addresses)}"
    
    # 【重要】一般的なブラウザを装うためのヘッダー
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # 【重要】getリクエストにheadersを追加して送信
        async with session.get(url, timeout=15, headers=headers) as response:
            response.raise_for_status()  # 4xx, 5xxエラーの場合は例外を発生させる
            data = await response.json()
            return data.get('pairs', [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        # 403エラーを含む接続エラーやタイムアウトを捕捉
        logging.error(f"DEX Screener API failed for {chain}: {e}. Proceeding without it.")
        return []

async def fetch_social_data(session, token_symbol):
    """
    Stocktwits/Reddit等のSNS APIを呼び出します。
    APIがメンテナンス中でもシステムが停止しないように設計されています。
    """
    # NOTE: この関数は現在ダミーです。
    # .envにAPIキーを設定した場合、ここに実際のAPI呼び出しロジックを追加してください。
    try:
        # 実際のAPI呼び出しをシミュレート
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return {"mentions": random.randint(10, 200), "status": "ok"}
    except Exception as e:
        logging.warning(f"Social media API is unavailable for ${token_symbol}. Reason: {e}. Proceeding without it.")
        return {"mentions": 0, "status": "unavailable"}

async def fetch_all_data_concurrently(target_pairs):
    """
    全ての外部APIからデータを並列で取得します。
    一部のAPIが失敗しても全体は停止せず、取得できたデータで処理を続行します。
    """
    async with aiohttp.ClientSession() as session:
        # DEX Screenerからの市場データ取得タスクを作成
        market_tasks = [fetch_dexscreener_data(session, chain, pairs) for chain, pairs in target_pairs.items() if pairs]
        market_results = await asyncio.gather(*market_tasks)
        
        all_pairs = [pair for chain_result in market_results for pair in chain_result]
        if not all_pairs: 
            return []

        # SNSデータ取得タスクを作成
        social_tasks = [fetch_social_data(session, pair['baseToken']['symbol']) for pair in all_pairs]
        social_results = await asyncio.gather(*social_tasks)

        # 取得した市場データとSNSデータをトークンごとに統合
        for i, pair in enumerate(all_pairs):
            pair['social_data'] = social_results[i]
            
        return all_pairs
