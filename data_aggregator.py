# data_aggregator.py
import pandas as pd
import logging
import yfinance as yf
from utils import api_retry_decorator
import ccxt

class DataAggregator:
    # ... (__init__と他の関数は変更なし)

    @api_retry_decorator(retries=3, delay=5)
    def get_historical_data(self, yf_ticker, period='1y'):
        """
        yfinanceから過去データを取得し、列名を安全に整形する。
        """
        logging.info(f"Fetching historical data for {yf_ticker}...")
        try:
            data = yf.download(yf_ticker, period=period, progress=False)
            if data.empty:
                return data

            # --- ▼▼▼ 修正箇所 ▼▼▼ ---
            # 列名が文字列であることと確認してから、整形処理を行う
            new_cols = []
            for col in data.columns:
                if isinstance(col, str):
                    new_cols.append(col.lower().replace(' ', '_'))
                else:
                    # 文字列でない場合は、元の名前をそのまま使う (あるいは適切な名前に変換)
                    new_cols.append(str(col)) # 最も安全なのは文字列に変換すること
            data.columns = new_cols
            # --- ▲▲▲ ここまで ▲▲▲ ---

            return data
        except Exception as e:
            # decoratorがリトライするため、ここではNoneを返して即時失敗させる
            logging.error(f"Critical error in get_historical_data for {yf_ticker}: {e}")
            return None # Noneを返すとdecoratorがリトライを試みる
