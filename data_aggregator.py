# data_aggregator.py
import pandas as pd
from pycoingecko import CoinGeckoAPI
import yfinance as yf
import requests
import logging

# 監視対象チェーンのCoinGecko APIにおけるID
CHAIN_IDS = {
    'ethereum': 'ethereum',
    'solana': 'solana',
    'base': 'base',
    'bnb-chain': 'binance-smart-chain',
    'arbitrum': 'arbitrum-one',
    'optimism': 'optimistic-ethereum',
    'polygon': 'polygon-pos',
    'avalanche': 'avalanche'
}

class DataAggregator:
    """
    市場データを様々なソースから収集・集約するクラス。
    - CoinGecko: 各チェーンのトップ銘柄の価格、出来高、変化率
    - yfinance: 個別銘柄の詳細な日足データ (OHLCV)
    - alternative.me: Fear & Greed Index
    """
    def __init__(self):
        self.cg = CoinGeckoAPI()
        logging.info("DataAggregator initialized.")

    def get_market_data(self, chain_id):
        """指定されたチェーンのトップ250銘柄の市場データを取得する"""
        logging.info(f"Fetching market data for {chain_id}...")
        try:
            # CoinGeckoからチェーン内のトップ250銘柄を取得
            coins = self.cg.get_coins_markets(vs_currency='usd', category=CHAIN_IDS[chain_id], per_page=250, page=1, price_change_percentage='1h,24h')
            if not coins:
                logging.warning(f"No coins data returned for {chain_id}.")
                return pd.DataFrame()
            
            df = pd.DataFrame(coins)
            
            # 必要なカラムに絞り込み、名前を変更
            df = df[['id', 'symbol', 'current_price', 'total_volume', 'price_change_percentage_24h_in_currency', 'price_change_percentage_1h_in_currency']]
            df.rename(columns={
                'price_change_percentage_24h_in_currency': 'price_change_24h',
                'price_change_percentage_1h_in_currency': 'price_change_1h'
            }, inplace=True)

            # TODO: ここで各銘柄のオンチェーンデータやSNS言及数を取得し、DataFrameに結合する
            # 例: df['onchain_volume_change'] = get_onchain_data(df['id'])
            # 例: df['sns_mentions'] = get_sns_mentions(df['symbol'])
            
            # 以下はダミーデータ (実際のAPIに置き換えてください)
            df['volume_change_24h'] = pd.Series(range(100, 100 + len(df) * 5, 5))
            df['volume_15m_multiple'] = pd.Series(range(1, 1 + int(len(df) * 0.1), 1)) * 0.1 + 1

            return df
        except Exception as e:
            logging.error(f"Failed to fetch market data for {chain_id}: {e}")
            return pd.DataFrame()

    def get_all_chains_data(self):
        """監視対象の全チェーンからデータを収集し、一つのDataFrameに統合する"""
        all_data = []
        for chain_name in CHAIN_IDS.keys():
            chain_data = self.get_market_data(chain_name)
            if not chain_data.empty:
                chain_data['chain'] = chain_name
                all_data.append(chain_data)
        
        if not all_data:
            logging.error("Failed to fetch data from any chain.")
            return pd.DataFrame()
        
        return pd.concat(all_data, ignore_index=True)

    def fetch_ohlcv(self, yf_ticker, period='1y'):
        """yfinanceから指定された銘柄の日足データ(OHLCV)を取得する"""
        logging.info(f"Fetching historical OHLCV data for {yf_ticker}...")
        try:
            data = yf.download(yf_ticker, period=period, progress=False)
            
            # yfinanceが返す複雑なカラム構造(MultiIndex)をシンプルな形式に変換する修正
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
            if data.empty or not required_cols.issubset(data.columns):
                logging.error(f"Failed to fetch valid OHLCV data for {yf_ticker}.")
                return pd.DataFrame()
                
            return data
        except Exception as e:
            logging.error(f"Error fetching OHLCV for {yf_ticker}: {e}")
            return pd.DataFrame()

    def get_fear_and_greed_index(self):
        """市場の恐怖と強欲指数 (Fear & Greed Index) を取得する"""
        logging.info("Fetching Fear & Greed Index...")
        try:
            response = requests.get("https://api.alternative.me/fng/?limit=1")
            response.raise_for_status() # HTTPエラーがあれば例外を発生
            data = response.json()['data'][0]
            value = int(data['value'])
            classification = data['value_classification']
            logging.info(f"Successfully fetched Fear & Greed Index: {value} ({classification})")
            return value, classification
        except Exception as e:
            logging.error(f"Failed to fetch Fear & Greed Index: {e}")
            return None, "Unknown"

