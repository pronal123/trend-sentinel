# data_aggregator.py
import pandas as pd
import logging
impo# data_aggregator.py
import pandas as pd
from pycoingecko import CoinGeckoAPI
import logging
import yfinance as yf
from utils import api_retry_decorator

class DataAggregator:
    def __init__(self, exchange_client=None):
        self.cg = CoinGeckoAPI()
        self.exchange = exchange_client

    @api_retry_decorator(retries=3, delay=5)
    def get_top_tokens(self, limit=50):
        # ... (変更なし)
        pass

    @api_retry_decorator(retries=3, delay=3)
    def get_latest_price(self, token_id):
        # ... (変更なし)
        pass

    @api_retry_decorator(retries=3, delay=5)
    def get_historical_data(self, yf_ticker, period='1y'):
        """
        yfinanceから過去データを取得し、複数階層の列名(MultiIndex)を安全に整形する。
        """
        logging.info(f"Fetching historical data for {yf_ticker}...")
        try:
            data = yf.download(yf_ticker, period=period, progress=False)
            if data.empty:
                return data

            # --- ▼▼▼ 修正箇所 ▼▼▼ ---
            # yfinance v0.2.38以降のMultiIndex形式に対応
            if isinstance(data.columns, pd.MultiIndex):
                # 列名をフラットにする (例: ('Open', 'BTC-USD') -> 'open')
                data.columns = data.columns.droplevel(1)
            
            # 列名を小文字のスネークケースに統一
            data.columns = [str(col).lower().replace(' ', '_') for col in data.columns]
            # --- ▲▲▲ ここまで ▲▲▲ ---

            return data
        except Exception as e:
            logging.error(f"Failed to fetch historical data for {yf_ticker}: {e}")
            return pd.DataFrame()
