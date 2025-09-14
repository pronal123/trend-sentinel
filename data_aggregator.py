# data_aggregator.py
import pandas as pd
from pycoingecko import CoinGeckoAPI
import logging
import yfinance as yf
from utils import api_retry_decorator
import ccxt

class DataAggregator:
    def __init__(self, exchange_client=None):
        """
        Constructor. Initializes the API clients and takes an exchange client.
        """
        self.cg = CoinGeckoAPI()
        self.exchange = exchange_client # Receives the ccxt instance from main.py

    @api_retry_decorator(retries=3, delay=5)
    def get_top_tokens(self, limit=50):
        logging.info(f"Fetching top {limit} tokens from CoinGecko...")
        tokens = self.cg.get_coins_markets(vs_currency='usd', per_page=limit, page=1)
        return tokens if tokens else []

    @api_retry_decorator(retries=3, delay=3)
    def get_latest_price(self, token_id):
        price_data = self.cg.get_price(ids=token_id, vs_currencies='usd')
        return price_data[token_id]['usd']

    @api_retry_decorator(retries=3, delay=5)
    def get_historical_data(self, yf_ticker, period='1y'):
        """
        Fetches historical data from yfinance and safely formats the column names.
        """
        logging.info(f"Fetching historical data for {yf_ticker}...")
        try:
            data = yf.download(yf_ticker, period=period, progress=False)
            if data.empty:
                return data

            # Handle MultiIndex columns from yfinance
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)
            
            # Safely format all columns to lowercase snake_case
            data.columns = [str(col).lower().replace(' ', '_') for col in data.columns]
            
            return data
        except Exception as e:
            logging.error(f"Failed to fetch historical data for {yf_ticker}: {e}")
            return pd.DataFrame()
