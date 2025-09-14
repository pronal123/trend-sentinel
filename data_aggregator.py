import requests
import yfinance as yf
import logging
from datetime import datetime, timedelta
import pytz
import ccxt
import random


class DataAggregator:
    def __init__(self):
        self.bitget = ccxt.bitget()
        self.coingecko_url = "https://api.coingecko.com/api/v3"

    # ==============================
    # BTC価格履歴（1分足）
    # ==============================
    def get_btc_price_history(self, minutes=60):
        try:
            df = yf.download("BTC-USD", period="1h", interval="1m")
            return df["Close"].tolist()
        except Exception as e:
            logging.error(f"BTC price history fetch failed: {e}")
            return []

    # ==============================
    # Fear & Greed Index
    # ==============================
    def get_fear_greed_index(self):
        try:
            res = requests.get("https://api.alternative.me/fng/")
            data = res.json()
            return {
                "value": data["data"][0]["value"],
                "classification": data["data"][0]["value_classification"]
            }
        except Exception as e:
            logging.error(f"Fear & Greed Index fetch failed: {e}")
            return {"value": None, "classification": "Unknown"}

    # ==============================
    # CoinGecko トレンド銘柄
    # ==============================
    def get_trending_coins(self, limit=5):
        try:
            res = requests.get(f"{self.coingecko_url}/search/trending")
            data = res.json()
            return [item["item"]["symbol"].upper() for item in data["coins"][:limit]]
        except Exception as e:
            logging.error(f"Trending coins fetch failed: {e}")
            return ["BTC"]

    # ==============================
    # ニュース記事（英語 & 日本語）
    # ==============================
    def get_news(self, limit=5):
        news = []
        try:
            # 英語ニュース（NewsAPI例: crypto）
            res = requests.get(
                "https://cryptopanic.com/api/v1/posts/?auth_token=demo&currencies=BTC"
            )
            if res.status_code == 200:
                data = res.json()
                for item in data.get("results", [])[:limit]:
                    news.append({"title": item["title"], "source": "CryptoPanic"})
        except Exception as e:
            logging.warning(f"English news fetch failed: {e}")

        try:
            # 日本語ニュース（CoinPost RSS）
            rss = requests.get("https://coinpost.jp/?feed=rss2")
            if rss.status_code == 200:
                from xml.etree import ElementTree as ET
                root = ET.fromstring(rss.content)
                for item in root.findall(".//item")[:limit]:
                    title = item.find("title").text
                    news.append({"title": title, "source": "CoinPost"})
        except Exception as e:
            logging.warning(f"Japanese news fetch failed: {e}")

        return news[:limit]

    # ==============================
    # 板の厚み分析（Bitget）
    # ==============================
    def get_orderbook_analysis(self, symbol="BTC/USDT"):
        try:
            orderbook = self.bitget.fetch_order_book(symbol, limit=50)
            bid_volume = sum([b[1] for b in orderbook["bids"]])
            ask_volume = sum([a[1] for a in orderbook["asks"]])
            imbalance = (bid_volume - ask_volume) / max(bid_volume + ask_volume, 1)
            return {
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "imbalance": imbalance
            }
        except Exception as e:
            logging.error(f"Orderbook fetch failed: {e}")
            return {"bid_volume": 0, "ask_volume": 0, "imbalance": 0}

    # ==============================
    # 利確／損切ポイント算出
    # ==============================
    def calc_takeprofit_stoploss(self, price, imbalance):
        tp = price * (1.02 + imbalance * 0.01)  # 板の厚みで調整
        sl = price * (0.98 - imbalance * 0.01)
        return round(tp, 2), round(sl, 2)

    # ==============================
    # コメント生成（AI風）
    # ==============================
    def generate_comment(self, symbol, price, orderbook, fg_index):
        if orderbook["imbalance"] > 0.2:
            bias = "買い支えが強く上昇しやすい"
        elif orderbook["imbalance"] < -0.2:
            bias = "売り圧力が強く下落注意"
        else:
            bias = "方向感は限定的"
        return (
            f"{symbol} の現在価格は {price} USD。"
            f"板状況は {bias}。恐怖指数は {fg_index['value']} ({fg_index['classification']})。"
            "利確・損切を意識しながら取引判断を。"
        )

    # ==============================
    # 総合スナップショット構築
    # ==============================
    def build_market_snapshot(self, state):
        snapshot = {}
        fg_index = self.get_fear_greed_index()
        trending = self.get_trending_coins()
        news = self.get_news()

        target_symbols = ["BTC/USDT"]
        target_symbols += [f"{sym}/USDT" for sym in trending]
        target_symbols += [f"{sym}/USDT" for sym in state.get_positions().keys()]
        target_symbols = list(set(target_symbols))  # 重複排除

        for sym in target_symbols:
            try:
                ticker = self.bitget.fetch_ticker(sym)
                price = ticker["last"]
                ob = self.get_orderbook_analysis(sym)
                tp, sl = self.calc_takeprofit_stoploss(price, ob["imbalance"])
                comment = self.generate_comment(sym, price, ob, fg_index)

                snapshot[sym] = {
                    "last_price": price,
                    "take_profit": tp,
                    "stop_loss": sl,
                    "orderbook": ob,
                    "fear_greed": fg_index,
                    "comment": comment,
                }
            except Exception as e:
                logging.warning(f"Snapshot error for {sym}: {e}")

        snapshot["_news"] = news
        snapshot["_updated_at"] = datetime.now(pytz.timezone("Asia/Tokyo")).isoformat()
        return snapshot
