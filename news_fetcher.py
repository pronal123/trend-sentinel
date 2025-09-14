import os
import logging
import requests
import feedparser
from googletrans import Translator

translator = Translator()

def get_latest_news():
    """英語(NewsAPI) + 日本語(RSS) ニュースをまとめて取得"""
    articles = []

    # --- 英語ニュース (NewsAPI) ---
    api_key = os.getenv("NEWSAPI_KEY")
    if api_key:
        try:
            url = f"https://newsapi.org/v2/everything?q=cryptocurrency&language=en&sortBy=publishedAt&pageSize=5&apiKey={api_key}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for a in data.get("articles", []):
                title_en = a.get("title", "")
                translated = translator.translate(title_en, src="en", dest="ja").text if title_en else ""
                articles.append({
                    "lang": "en",
                    "title_en": title_en,
                    "title_ja": translated,
                    "source": a.get("source", {}).get("name"),
                    "url": a.get("url"),
                    "publishedAt": a.get("publishedAt")
                })
        except Exception as e:
            logging.error(f"Failed to fetch NewsAPI news: {e}")

    # --- 日本語ニュース (CoinPost, CryptoTimes RSS) ---
    rss_feeds = {
        "CoinPost": "https://coinpost.jp/?feed=rss2",
        "CryptoTimes": "https://crypto-times.jp/feed/"
    }
    for source, url in rss_feeds.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                articles.append({
                    "lang": "ja",
                    "title": entry.title,
                    "source": source,
                    "url": entry.link,
                    "publishedAt": entry.get("published", "")
                })
        except Exception as e:
            logging.error(f"Failed to fetch RSS ({source}): {e}")

    return articles
