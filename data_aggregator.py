# data_aggregator.py
import os
import pandas as pd
from pycoingecko import CoinGeckoAPI
import logging

# ... (CHAIN_IDSは変更なし)

class DataAggregator:
    def __init__(self):
        self.moralis_api_key = os.environ.get("MORALIS_API_KEY")
        proxy_url = os.environ.get("PROXY_URL")
        
        # プロキシが設定されていれば、それをrequestsセッションに組み込む
        session_kwargs = {}
        if proxy_url:
            session_kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
            logging.info("Proxy configured for data aggregation.")
            
        self.cg = CoinGeckoAPI(session_kwargs=session_kwargs)

    def get_onchain_data(self, token_ids):
        """Moralis APIを使ってオンチェーンデータを取得する（ダミー実装）"""
        if not self.moralis_api_key:
            logging.warning("Moralis API key not found. Skipping on-chain data.")
            return pd.DataFrame()
        
        # TODO: Moralis SDKやAPIを呼び出し、token_idsに対応するデータを取得する
        # 例: トランザクション数、アクティブウォレット数など
        logging.info(f"Fetching on-chain data for {len(token_ids)} tokens via Moralis...")
        # 以下はダミーデータ
        onchain_df = pd.DataFrame({
            'id': token_ids,
            'active_wallets_24h': [100 + i*10 for i in range(len(token_ids))]
        })
        return onchain_df

    def get_market_data(self, chain_id):
        # ... (CoinGeckoからのデータ取得ロジックはほぼ同じ)
        # 取得したデータにオンチェーンデータを結合する
        try:
            coins = self.cg.get_coins_markets(...)
            if not coins: return pd.DataFrame()
            df = pd.DataFrame(coins)
            # ... (カラム名変更など)

            # オンチェーンデータを取得して結合
            onchain_data = self.get_onchain_data(df['id'].tolist())
            if not onchain_data.empty:
                df = pd.merge(df, onchain_data, on='id', how='left')

            return df
        except Exception as e:
            # ...
            return pd.DataFrame()

    # ... (get_all_chains_dataは変更なし)
