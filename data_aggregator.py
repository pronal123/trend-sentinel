# data_aggregator.py
import logging
import requests
import feedparser
from datetime import datetime, timedelta

# optional libs; import with try/except to degrade gracefully in environments lacking them
try:
    import yfinance as yf
except Exception:
    yf = None

try:
    from googletrans import Translator
    translator = Translator()
except Exception:
    translator = None

import pandas as pd

logger = logging.getLogger(__name__)


class DataAggregator:
    """
    市場データを集約するユーティリティクラス。
    - BTCの価格履歴取得（yfinance）
    - Fear & Greed Index（alternative.me）
    - CoinGecko trending coins
    - ニュース（NewsAPI -> 英語 -> 翻訳）、および日本語RSS
    """

    def __init__(self):
        # ここで必要な初期設定があれば
        pass

    # -----------------------
    # BTC 価格履歴 (yfinance を利用)
    # -----------------------
    def get_price_history(self, symbol="BTC-USD", period="1d", interval="1h"):
        """
        BTC価格履歴を取得して、フロントに渡す辞書を返す。
        戻り値:
            {"timestamps": [...], "prices": [...]}
        """
        if yf is None:
            logger.warning("yfinance not available. Returning empty price history.")
            return {"timestamps": [], "prices": []}

        try:
            # yfinance の ticker.history は timezone aware な DatetimeIndex を返す
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            if hist.empty:
                logger.warning("yfinance returned empty history")
                return {"timestamps": [], "prices": []}

            # 日時ラベルと終値
            timestamps = [ts.strftime("%Y-%m-%d %H:%M") for ts in hist.index.to_pydatetime()]
            prices = [float(round(v, 2)) for v in hist["Close"].tolist()]
            return {"timestamps": timestamps, "prices": prices}
        except Exception as e:
            logger.error(f"Failed to fetch price history: {e}", exc_info=True)
            return {"timestamps": [], "prices": []}

    # -----------------------
    # Fear & Greed Index (alternative.me)
    # -----------------------
    def get_fear_and_greed_index(self):
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            if "data" in data and data["data"]:
                item = data["data"][0]
                return {
                    "value": item.get("value"),
                    "classification": item.get("value_classification"),
                    "timestamp": item.get("timestamp"),
                }
        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed Index: {e}")
        return {"value": None, "classification": None, "timestamp": None}

    # -----------------------
    # CoinGecko: trending coins
    # -----------------------
    def get_trending_coins(self):
        try:
            url = "https://api.coingecko.com/api/v3/search/trending"
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            coins = []
            for item in data.get("coins", []):
                c = item.get("item", {})
                coins.append({
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "symbol": c.get("symbol"),
                    "market_cap_rank": c.get("market_cap_rank"),
                    "thumb": c.get("thumb"),
                })
            return coins
        except Exception as e:
            logger.warning(f"Failed to fetch trending coins: {e}")
            return []

    # -----------------------
    # News: 英語(NewsAPI) + 日本語RSS (CoinPost, CryptoTimes)
    # - 英語記事は翻訳 (googletrans) が可能なら title_ja を追加
    # -----------------------
    def get_latest_news(self, newsapi_key=None, english_limit=5, japanese_limit=5):
        all_articles = []

        # --- 英語ニュース via NewsAPI ---
        if newsapi_key:
            try:
                q = "cryptocurrency OR bitcoin OR ethereum OR crypto"
                url = "https://newsapi.org/v2/everything"
                params = {
                    "q": q,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": english_limit,
                    "apiKey": newsapi_key
                }
                resp = requests.get(url, params=params, timeout=8)
                resp.raise_for_status()
                data = resp.json()
                for a in data.get("articles", []):
                    title_en = a.get("title")
                    title_ja = None
                    if translator is not None and title_en:
                        try:
                            # translator may be slow; we catch errors
                            title_ja = translator.translate(title_en, src="en", dest="ja").text
                        except Exception:
                            title_ja = None
                    all_articles.append({
                        "lang": "en",
                        "title_en": title_en,
                        "title_ja": title_ja,
                        "source": a.get("source", {}).get("name"),
                        "url": a.get("url"),
                        "publishedAt": a.get("publishedAt")
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch english news from NewsAPI: {e}")

        # --- 日本語RSS (CoinPost, CryptoTimes) ---
        rss_feeds = {
            "CoinPost": "https://coinpost.jp/?feed=rss2",
            "CryptoTimes": "https://crypto-times.jp/feed/"
        }
        for source, feed_url in rss_feeds.items():
            try:
                feed = feedparser.parse(feed_url)
                count = 0
                for entry in feed.entries:
                    if count >= japanese_limit:
                        break
                    title = entry.get("title")
                    link = entry.get("link")
                    published = entry.get("published", "") or entry.get("updated", "")
                    all_articles.append({
                        "lang": "ja",
                        "title": title,
                        "source": source,
                        "url": link,
                        "publishedAt": published
                    })
                    count += 1
            except Exception as e:
                logger.warning(f"Failed to fetch RSS from {source}: {e}")

        # trim to (english_limit + japanese_limit) may produce > limits because we append both lists,
        # but we intentionally capped per-source.
        return all_articles

    # -----------------------
    # get_latest_price: friend for trading_executor
    # try query Coingecko simple price as fallback
    # -----------------------
    def get_latest_price(self, coingecko_id):
        """
        coingecko_id (eg. 'bitcoin', 'ethereum') -> try CoinGecko simple/price API
        returns float price in USD or None
        """
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": coingecko_id, "vs_currencies": "usd"}
            r = requests.get(url, params=params, timeout=6)
            r.raise_for_status()
            data = r.json()
            price = data.get(coingecko_id, {}).get("usd")
            if price is not None:
                return float(price)
        except Exception as e:
            logger.debug(f"CoinGecko simple price failed for {coingecko_id}: {e}")
        return None
