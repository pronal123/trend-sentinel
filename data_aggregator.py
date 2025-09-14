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
        コンストラクタ。取引所クライアントを受け取り、APIを初期化する。
        """
        self.cg = CoinGeckoAPI()
        self.exchange = exchange_client # main.pyからccxtインスタンスを受け取る

    @api_retry_decorator(retries=3, delay=5)
    def get_top_tokens(self, limit=50):
        logging.info(f"Fetching top {limit} tokens from CoinGecko...")
        tokens = self.cg.get_coins_markets(vs_currency='usd', per_page=limit, page=1)
        return tokens if tokens else []

    @api_retry_decorator(retries=3, delay=3)
    def get_latest_price(self, token_id):
        price_data = self.cg.get_price(ids=token_id, vs_currencies='usd')
        return price_data[token_id]['usd']

    def get_historical_data(self, yf_ticker, period='1y'):
        """
        yfinanceから過去データを取得。失敗した場合は取引所から取得を試みる。
        """
        logging.info(f"Attempting to fetch historical data for {yf_ticker} from yfinance...")
        try:
            data = yf.download(yf_ticker, period=period, progress=False)
            if not data.empty:
                data.columns = [col.lower().replace(' ', '_') for col in data.columns]
                logging.info("Successfully fetched data from yfinance.")
                return data
        except Exception as e:
            logging.warning(f"yfinance download failed: {e}. Trying exchange as a fallback.")

        # --- yfinanceが失敗した場合のフォールバック処理 ---
        if self.exchange:
            try:
                ccxt_ticker = yf_ticker.replace('-', '/') # yfinance形式をccxt形式に変換
                logging.info(f"Attempting to fetch historical data for {ccxt_ticker} from exchange...")
                
                # 1日足のOHLCVデータを取得 (limitは取引所による)
                ohlcv = self.exchange.fetch_ohlcv(ccxt_ticker, '1d', limit=365)
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    logging.info("Successfully fetched data from exchange as a fallback.")
                    return df
            except Exception as e:
                logging.error(f"Exchange fallback also failed for {yf_ticker}: {e}")
        
        logging.error(f"All methods failed to fetch historical data for {yf_ticker}.")
        return pd.DataFrame()
