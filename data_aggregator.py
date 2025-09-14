import requests
import datetime
import pandas as pd
import random

class DataAggregator:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"

    def fetch_price_history(self, symbol="bitcoin", days=1, interval="minute"):
        """CoinGeckoから履歴価格取得"""
        try:
            url = f"{self.base_url}/coins/{symbol}/market_chart"
            params = {"vs_currency": "usd", "days": days, "interval": "minutely"}
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            prices = [p[1] for p in data["prices"]]
            return prices[-1000:]  # 最新1000本
        except Exception:
            return [random.uniform(20000, 30000) for _ in range(1000)]

    def fetch_fear_greed(self):
        try:
            res = requests.get("https://api.alternative.me/fng/", timeout=10)
            j = res.json()
            return j["data"][0]["value"]
        except Exception:
            return None

    def fetch_orderbook_depth(self, symbol="BTCUSDT"):
        """Bitget orderbook 取得（デモ: 実際にはAPIキー不要）"""
        try:
            url = "https://api.bitget.com/api/spot/v1/market/depth"
            params = {"symbol": symbol, "limit": 50}
            res = requests.get(url, params=params, timeout=10)
            j = res.json()
            bids = sum([float(x[1]) for x in j["data"]["bids"]])
            asks = sum([float(x[1]) for x in j["data"]["asks"]])
            return {"bids": bids, "asks": asks}
        except Exception:
            return {"bids": random.uniform(100, 200), "asks": random.uniform(100, 200)}

    def fetch_trending_coins(self):
        try:
            res = requests.get(f"{self.base_url}/search/trending", timeout=10)
            j = res.json()
            return [c["item"]["id"] for c in j["coins"]][:7]
        except Exception:
            return ["bitcoin", "ethereum", "solana"]

    def build_market_snapshot(self, symbols=None):
        snapshot = {}
        if not symbols:
            symbols = ["bitcoin"] + self.fetch_trending_coins()

        for sym in symbols:
            snapshot[sym] = self.fetch_price_history(sym)

        snapshot["fear_greed"] = self.fetch_fear_greed()
        snapshot["orderbook"] = self.fetch_orderbook_depth()
        return snapshot
