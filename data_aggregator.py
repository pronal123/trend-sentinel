# data_aggregator.py (抜粋)
import requests
import ccxt
import os
import pandas as pd
from datetime import datetime

class DataAggregator:
    def __init__(self):
        self.ex = ccxt.bitget({"enableRateLimit": True})
        self.moralis_key = os.getenv("MORALIS_API_KEY")
        self.newsapi_key = os.getenv("NEWSAPI_KEY")

    def fetch_fear_and_greed(self):
        try:
            res = requests.get("https://api.alternative.me/fng/?limit=1")
            return res.json()["data"][0]
        except Exception:
            return {"value": None}

    def fetch_price_ohlcv_ccxt(self, symbol, timeframe="1m", limit=60):
        try:
            ohlcv = self.ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","volume"])
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            return df
        except Exception:
            return pd.DataFrame()

    def fetch_orderbook_summary(self, symbol, limit=20):
        try:
            ob = self.ex.fetch_order_book(symbol, limit=limit)
            buy_vol = sum([b[1] for b in ob["bids"]])
            sell_vol = sum([a[1] for a in ob["asks"]])
            ratio = (buy_vol / (buy_vol + sell_vol)) * 100 if buy_vol+sell_vol>0 else 50
            return {"buy_volume": buy_vol, "sell_volume": sell_vol, "buy_ratio": ratio}
        except Exception:
            return {}

    def fetch_onchain_metrics(self, token_address, chain="eth"):
        """Moralis を使ったオンチェーンデータ例"""
        try:
            url = f"https://deep-index.moralis.io/api/v2/erc20/{token_address}/price?chain={chain}"
            headers = {"X-API-Key": self.moralis_key}
            res = requests.get(url, headers=headers, timeout=10)
            return res.json()
        except Exception:
            return {}

    def fetch_news(self, query="crypto"):
        news_list = []
        # 英語: NewsAPI
        try:
            url = f"https://newsapi.org/v2/everything?q={query}&language=en&sortBy=publishedAt&pageSize=3&apiKey={self.newsapi_key}"
            res = requests.get(url).json()
            for a in res.get("articles", []):
                news_list.append({"title": a["title"], "source": a["source"]["name"], "url": a["url"], "lang": "en"})
        except Exception:
            pass
        # 日本語: CoinPost / CryptoTimes
        try:
            jp_sources = [
                "https://coinpost.jp/?feed=rss2",
                "https://crypto-times.jp/feed/",
            ]
            import feedparser
            for src in jp_sources:
                feed = feedparser.parse(src)
                for entry in feed.entries[:3]:
                    news_list.append({"title": entry.title, "source": entry.get("source","JP"), "url": entry.link, "lang": "ja"})
        except Exception:
            pass
        return news_list[:5]

    def build_market_snapshot(self, symbols):
        snapshot = {}
        for sym in symbols:
            try:
                df = self.fetch_price_ohlcv_ccxt(sym, "1m", 60)
                latest_price = df["close"].iloc[-1] if not df.empty else None
                ob = self.fetch_orderbook_summary(sym)
                snapshot[sym] = {
                    "latest_price": latest_price,
                    "history": df[["ts","close"]].values.tolist() if not df.empty else [],
                    "orderbook": ob,
                }
            except Exception:
                snapshot[sym] = {}
        # add news + onchain as extra
        snapshot["news"] = self.fetch_news()
        return snapshot
