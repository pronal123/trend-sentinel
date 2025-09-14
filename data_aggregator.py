# data_aggregator.py
import os
import pandas as pd
from pycoingecko import CoinGeckoAPI
import logging
import yfinance as yf
from utils import api_retry_decorator

class DataAggregator:
    def __init__(self):
        self.cg = CoinGeckoAPI()

    @api_retry_decorator(retries=3, delay=5)
    def get_top_tokens(self, limit=50):
        logging.info(f"Fetching top {limit} tokens from CoinGecko...")
        return self.cg.get_coins_markets(vs_currency='usd', per_page=limit, page=1)

    @api_retry_decorator(retries=3, delay=5)
    def get_latest_price(self, token_id):
        price_data = self.cg.get_price(ids=token_id, vs_currencies='usd')
        return price_data[token_id]['usd']

    @api_retry_decorator(retries=3, delay=5)
    def get_historical_data(self, yf_ticker, period='1y'):
        logging.info(f"Fetching historical data for {yf_ticker}...")
        data = yf.download(yf_ticker, period=period, progress=False)
        if data.empty: return data
        data.columns = [col.lower().replace(' ', '_') for col in data.columns]
        return data
