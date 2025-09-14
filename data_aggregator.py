import logging, time, requests
import ccxt
import pandas as pd
from datetime import datetime, timezone

from config import FNG_URL, COVALENT_API_KEY

class DataAggregator:
    def __init__(self):
        # CCXT exchange client (bitget) for prices/orderbook/OHLCV
        try:
            self.ex = ccxt.bitget({'enableRateLimit': True})
            self.ex.load_markets()
            logging.info("Initialized bitget client")
        except Exception as e:
            logging.error("Failed init exchange client: %s", e)
            self.ex = None

    # CoinGecko for token list / simple market info (if needed) - they don't need key
    def fetch_price_ohlcv_ccxt(self, symbol, timeframe="1m", limit=60):
        """Fetch recent OHLCV from bitget (or exchange). symbol must be like 'BTC/USDT'"""
        if not self.ex: return pd.DataFrame()
        try:
            raw = self.ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume"])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
            return df
        except Exception as e:
            logging.error("fetch_ohlcv fail %s: %s", symbol, e)
            return pd.DataFrame()

    def fetch_orderbook_summary(self, symbol, depth=50):
        if not self.ex: return {}
        try:
            ob = self.ex.fetch_order_book(symbol, limit=depth)
            buy = sum([b[1] for b in ob.get('bids',[])])
            sell = sum([a[1] for a in ob.get('asks',[])])
            total = buy + sell
            ratio = round((buy/total*100) if total>0 else 0, 2)
            return {"buy_volume":round(buy,6),"sell_volume":round(sell,6),"buy_ratio":ratio}
        except Exception as e:
            logging.error("fetch_orderbook fail %s: %s", symbol, e)
            return {}

    def fetch_fear_and_greed(self):
        try:
            r = requests.get(FNG_URL, timeout=10).json()
            d = r.get("data",[{}])[0]
            return {"value": int(d.get("value",0)), "classification": d.get("value_classification","N/A")}
        except Exception as e:
            logging.error("Failed FNG: %s", e)
            return {"value": None, "classification":"N/A"}

    def fetch_news(self, q="crypto", language="en", page_size=5):
        """Use NewsAPI if available (English) — fallback empty list"""
        # (the caller should provide NEWSAPI_KEY via config or env)
        from config import NEWSAPI_KEY
        if not NEWSAPI_KEY:
            return []
        try:
            url = "https://newsapi.org/v2/everything"
            params = {"q": q, "language": language, "pageSize": page_size, "sortBy":"publishedAt", "apiKey": NEWSAPI_KEY}
            r = requests.get(url, params=params, timeout=10).json()
            items = []
            for a in r.get("articles",[]):
                items.append({"title": a.get("title"), "url": a.get("url"), "source": a.get("source",{}).get("name")})
            return items
        except Exception as e:
            logging.error("newsapi fail: %s", e)
            return []

    # helper to build market snapshot for symbols list
    def build_market_snapshot(self, symbols):
        out = {}
        for s in symbols:
            df = self.fetch_price_ohlcv_ccxt(s, timeframe="1m", limit=60)
            if df.empty:
                out[s] = {"latest_price": None, "history": [], "orderbook": {}}
                continue
            history = [[row['ts'].isoformat(), float(row['close'])] for _, row in df.iterrows()]
            out[s] = {
                "latest_price": float(df['close'].iloc[-1]),
                "history": history,
                "orderbook": self.fetch_orderbook_summary(s)
            }
        return out
