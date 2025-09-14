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
    """
    def __init__(self):
        self.cg = CoinGeckoAPI()
        logging.info("DataAggregator initialized.")

    def get_market_data(self, chain_id):
        """指定されたチェーンのトップ250銘柄の市場データを取得する"""
        logging.info(f"Fetching market data for {chain_id}...")
        try:
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

            # ダミーデータ (実際のAPIに置き換えてください)
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

    def fetch_ohlcv(self, yf_ticker, period='1y', interval='1d'):
        """yfinanceから指定された銘柄のOHLCVデータを取得する"""
        logging.info(f"Fetching historical OHLCV data for {yf_ticker} ({period}, {interval})...")
        try:
            data = yf.download(yf_ticker, period=period, interval=interval, progress=False, auto_adjust=True)
            if data.empty:
                 return pd.DataFrame()

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            
            # カラム名を大文字始まりに統一 (例: 'open' -> 'Open')
            data.columns = [col.capitalize() for col in data.columns]
            
            if not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(data.columns):
                return pd.DataFrame()

            return data
        except Exception as e:
            logging.error(f"Error fetching OHLCV for {yf_ticker}: {e}")
            return pd.DataFrame()

    def get_fear_and_greed_index(self):
        """市場の恐怖と強欲指数 (Fear & Greed Index) を取得する"""
        logging.info("Fetching Fear & Greed Index...")
        try:
            response = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            response.raise_for_status()
            data = response.json()['data'][0]
            return int(data['value']), data['value_classification']
        except Exception as e:
            logging.error(f"Failed to fetch Fear & Greed Index: {e}")
            return None, "Unknown"

    def get_latest_price(self, token_id):
        """指定された単一トークンIDの最新USD価格を取得する"""
        try:
            price_data = self.cg.get_price(ids=token_id, vs_currencies='usd')
            if token_id in price_data and 'usd' in price_data[token_id]:
                return price_data[token_id]['usd']
            else:
                logging.warning(f"Price data not found for token_id: {token_id}")
                return None
        except Exception as e:
            logging.error(f"Failed to fetch latest price for {token_id}: {e}")
            return None
