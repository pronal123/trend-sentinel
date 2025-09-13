# data_aggregator.py
import pandas as pd
from pycoingecko import CoinGeckoAPI
import logging

CHAIN_IDS = {
    'ethereum': 'ethereum', 'solana': 'solana', 'base': 'base',
    'bnb-chain': 'binance-smart-chain', 'arbitrum': 'arbitrum-one',
    'optimism': 'optimistic-ethereum', 'polygon': 'polygon-pos', 'avalanche': 'avalanche'
}

class DataAggregator:
    def __init__(self):
        self.cg = CoinGeckoAPI()

    def get_market_data(self, chain_id):
        logging.info(f"Fetching market data for {chain_id}...")
        try:
            coins = self.cg.get_coins_markets(vs_currency='usd', category=CHAIN_IDS[chain_id], per_page=250, page=1)
            if not coins: return pd.DataFrame()
            
            df = pd.DataFrame(coins)
            df = df[['id', 'symbol', 'current_price', 'total_volume', 'price_change_percentage_24h', 'price_change_percentage_1h_in_currency']]
            df.rename(columns={
                'price_change_percentage_24h': 'price_change_24h',
                'price_change_percentage_1h_in_currency': 'price_change_1h'
            }, inplace=True)

            # TODO: オンチェーンデータやSNS言及数を取得し結合
            df['volume_change_24h'] = [100 + i * 5 for i in range(len(df))] # ダミー
            df['volume_15m_multiple'] = [1 + i * 0.1 for i in range(len(df))] # ダミー
            return df
        except Exception as e:
            logging.error(f"Failed to fetch data for {chain_id}: {e}")
            return pd.DataFrame()

    def get_all_chains_data(self):
        all_data = [self.get_market_data(name) for name, cid in CHAIN_IDS.items()]
        valid_data = [df for df in all_data if not df.empty]
        if not valid_data: return pd.DataFrame()
        return pd.concat(valid_data, ignore_index=True)
