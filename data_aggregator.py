import ccxt
import logging
import pandas as pd
import requests
from datetime import datetime, timezone

class DataAggregator:
    """
    Bitget を利用して 1分足OHLCV・板情報を取得。
    BTC/USDTは常時、ポジション保有時はその銘柄も取得対象にする。
    """
    def __init__(self):
        try:
            self.exchange = ccxt.bitget({"enableRateLimit": True})
            self.exchange.load_markets()
            logging.info("DataAggregator initialized with Bitget.")
        except Exception as e:
            logging.error(f"Failed to init Bitget exchange: {e}")
            self.exchange = None

    def fetch_ohlcv(self, symbol: str, limit: int = 60):
        """Bitgetから1分足OHLCVを取得"""
        if not self.exchange:
            return []
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe="1m", limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            return df
        except Exception as e:
            logging.error(f"fetch_ohlcv failed for {symbol}: {e}")
            return []

    def fetch_orderbook_summary(self, symbol: str, depth: int = 50):
        """板の厚さを集計"""
        if not self.exchange:
            return {}
        try:
            ob = self.exchange.fetch_order_book(symbol, limit=depth)
            buy_volume = sum([b[1] for b in ob["bids"]])
            sell_volume = sum([a[1] for a in ob["asks"]])
            total = buy_volume + sell_volume
            ratio = (buy_volume / total * 100) if total > 0 else 0
            return {
                "buy_volume": round(buy_volume, 2),
                "sell_volume": round(sell_volume, 2),
                "buy_ratio": round(ratio, 1),
            }
        except Exception as e:
            logging.error(f"fetch_orderbook_summary failed for {symbol}: {e}")
            return {}

    def fetch_fear_greed_index(self):
        """Fear & Greed Index (Alternative.me API)"""
        try:
            url = "https://api.alternative.me/fng/"
            r = requests.get(url, timeout=10)
            data = r.json()["data"][0]
            return {
                "value": int(data["value"]),
                "classification": data["value_classification"]
            }
        except Exception as e:
            logging.error(f"fetch_fear_greed_index failed: {e}")
            return {}

    def get_market_snapshot(self, symbols: list):
        """複数シンボルの価格履歴＋板厚サマリを返す"""
        result = {}
        for sym in symbols:
            df = self.fetch_ohlcv(sym)
            if isinstance(df, pd.DataFrame) and not df.empty:
                latest_price = float(df["close"].iloc[-1])
                history = df[["timestamp","close"]].tail(60).values.tolist()
                history_fmt = [
                    [ts.isoformat(), float(price)] for ts, price in history
                ]
                orderbook = self.fetch_orderbook_summary(sym)
                result[sym] = {
                    "latest_price": latest_price,
                    "history": history_fmt,
                    "orderbook": orderbook
                }
        return result
