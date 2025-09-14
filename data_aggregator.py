# data_aggregator.py
import pandas as pd
from pycoingecko import CoinGeckoAPI
import yfinance as yf
import requests
import logging

CHAIN_IDS = {
    'ethereum': 'ethereum', 'solana': 'solana', 'base': 'base',
    'bnb-chain': 'binance-smart-chain', 'arbitrum': 'arbitrum-one',
    'optimism': 'optimistic-ethereum', 'polygon': 'polygon-pos', 'avalanche': 'avalanche'
}

class DataAggregator:
    def __init__(self):
        self.cg = CoinGeckoAPI()
        logging.info("DataAggregator initialized.")

    def get_market_data(self, chain_id):
        try:
            coins = self.cg.get_coins_markets(
                vs_currency='usd',
                category=CHAIN_IDS.get(chain_id),
                per_page=250,
                page=1,
                price_change_percentage='1h,24h'
            )
            if not coins:
                return pd.DataFrame()
            df = pd.DataFrame(coins)
            df = df[['id', 'symbol', 'current_price', 'total_volume',
                     'price_change_percentage_24h_in_currency', 'price_change_percentage_1h_in_currency']]
            df.rename(columns={
                'price_change_percentage_24h_in_currency': 'price_change_24h',
                'price_change_percentage_1h_in_currency': 'price_change_1h'
            }, inplace=True)
            df['volume_change_24h'] = pd.Series(range(100, 100 + len(df) * 5, 5))
            df['volume_15m_multiple'] = pd.Series(range(1, 1 + int(len(df) * 0.1), 1)) * 0.1 + 1
            return df
        except Exception as e:
            logging.error(f"Failed to fetch market data for {chain_id}: {e}")
            return pd.DataFrame()

    def get_all_chains_data(self):
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

    # ▼▼▼ テクニカル指標の追加関数 ▼▼▼

    def add_technical_indicators(self, df):
        if 'Close' not in df.columns:
            logging.error("Missing 'Close' column for technical indicator calculation.")
            return df

        # EMA
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()

        # SMA
        df['SMA_20'] = df['Close'].rolling(window=20).mean()

        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df['RSI_14'] = 100 - (100 / (1 + rs))

        # MACD and Signal line
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # Bollinger Band Width
        ma = df['Close'].rolling(window=20).mean()
        std = df['Close'].rolling(window=20).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        df['BBB_20_2.0'] = (upper - lower) / ma

        logging.info("All technical indicators calculated.")
        return df

    def fetch_ohlcv(self, yf_ticker, period='1y', interval='1d'):
        try:
            data = yf.download(
                yf_ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True
            )
            if data.empty:
                return pd.DataFrame()

            # Capitalize column names
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            data.columns = [col.capitalize() for col in data.columns]

            required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
            if not required_cols.issubset(data.columns):
                logging.error(f"Missing required OHLCV columns: {required_cols - set(data.columns)}")
                return pd.DataFrame()

            # ✅ 自動的にテクニカル指標を追加
            data = self.add_technical_indicators(data)

            return data

        except Exception as e:
            logging.error(f"Error fetching OHLCV for {yf_ticker}: {e}")
            return pd.DataFrame()

    def get_fear_and_greed_index(self):
        try:
            response = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            response.raise_for_status()
            data = response.json()['data'][0]
            return int(data['value']), data['value_classification']
        except Exception as e:
            logging.error(f"Failed to fetch Fear & Greed Index: {e}")
            return None, "Unknown"

    def get_latest_price(self, token_id):
        try:
            price_data = self.cg.get_price(ids=token_id, vs_currencies='usd')
            if token_id in price_data and 'usd' in price_data[token_id]:
                return price_data[token_id]['usd']
            return None
        except Exception:
            return None
