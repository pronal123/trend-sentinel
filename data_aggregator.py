# data_aggregator.py
import os
import pandas as pd
from pycoingecko import CoinGeckoAPI
import logging
import yfinance as yf
import requests

class DataAggregator:
    def __init__(self):
        self.cg = CoinGeckoAPI()
        self.moralis_api_key = os.environ.get("MORALIS_API_KEY")
        self.cryptocompare_api_key = os.environ.get("CRYPTOCOMPARE_API_KEY")

    def get_top_tokens(self, limit=50):
        """CoinGeckoから時価総額上位のトークンリストを取得する"""
        try:
            logging.info(f"Fetching top {limit} tokens from CoinGecko...")
            # vs_currencyはusd, per_pageで取得数を指定
            top_tokens = self.cg.get_coins_markets(vs_currency='usd', per_page=limit, page=1)
            return top_tokens
        except Exception as e:
            logging.error(f"Failed to fetch top tokens: {e}")
            return []
            
    def get_latest_price(self, token_id):
        """指定されたトークンの最新価格を取得する"""
        try:
            price_data = self.cg.get_price(ids=token_id, vs_currencies='usd')
            return price_data[token_id]['usd']
        except Exception as e:
            logging.error(f"Could not get latest price for {token_id}: {e}")
            return None

    def get_historical_data(self, yf_ticker, period='1y'):
        """yfinanceを使用して、指定されたティッカーの過去の時系列データを取得する"""
        try:
            logging.info(f"Fetching historical data for {yf_ticker}...")
            # progress=Falseでダウンロードバーを非表示にする
            data = yf.download(yf_ticker, period=period, progress=False)
            return data
        except Exception as e:
            logging.error(f"Failed to fetch historical data for {yf_ticker}: {e}")
            return pd.DataFrame()
