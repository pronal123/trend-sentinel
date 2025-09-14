# data_aggregator.py
import os
import time
import logging
import requests
from datetime import datetime, timezone
import openai
import yfinance as yf
import pandas as pd
import math
import ccxt

# 環境変数からキーを読む
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # optional fallback usage
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

class DataAggregator:
    """Market data & AI prompt helper."""

    def __init__(self, state_manager):
        self.state = state_manager
        # chain perf local cache to avoid too many Moralis requests (kept in state manager too)
        self._local_chain_cache = {"data": {}, "timestamp": 0}
        self._local_chain_cache_ttl = 300  # 5 minutes

    # ------------------------
    # BTC 1分足取得 (yfinance)
    # ------------------------
    def fetch_btc_ohlcv_1m(self, period="1d", interval="1m") -> pd.DataFrame:
        """
        Returns recent BTC-USD OHLCV as pandas DataFrame (index=Datetime).
        Uses yfinance and returns DataFrame with columns: open, high, low, close, volume
        """
        try:
            ticker = yf.Ticker("BTC-USD")
            df = ticker.history(period=period, interval=interval, actions=False)
            if df.empty:
                return pd.DataFrame()
            df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            # keep only required columns
            df = df[["open", "high", "low", "close", "volume"]]
            return df
        except Exception as e:
            logging.error(f"Failed to fetch BTC OHLCV: {e}")
            return pd.DataFrame()

    # ------------------------
    # Fear & Greed Index (Alternative.me)
    # ------------------------
    def get_fear_and_greed_index(self):
        """
        Returns tuple (value:int, sentiment:str)
        """
        try:
            r = requests.get("https://api.alternative.me/fng/", timeout=10)
            if r.status_code == 200:
                j = r.json()
                data = j.get("data", [])
                if data:
                    v = int(data[0].get("value", 50))
                    sentiment = data[0].get("value_classification", "Neutral")
                    return v, sentiment
        except Exception as e:
            logging.warning(f"Failed to fetch Fear & Greed: {e}")
        return None, "Unknown"

    # ------------------------
    # CoinGecko trending symbols
    # ------------------------
    def get_coingecko_trending_symbols(self, top_n=5):
        try:
            r = requests.get(f"{COINGECKO_API_BASE}/search/trending", timeout=10)
            if r.status_code == 200:
                j = r.json()
                coins = j.get("coins", [])[:top_n]
                symbols = []
                for c in coins:
                    item = c.get("item", {})
                    # symbol may be lowercase -> upper
                    sym = item.get("symbol", "")
                    if sym:
                        symbols.append(sym.upper())
                return symbols
        except Exception as e:
            logging.warning(f"CoinGecko trending fetch failed: {e}")
        return []

    # ------------------------
    # Chain performance via Moralis (with CoinGecko fallback). 5min cache.
    # ------------------------
    def get_chain_performance(self, chains):
        """
        chains: list of chain identifiers strings used for Moralis and CoinGecko mapping
        returns dict { chain: perf_24h_percent (float) }
        Caches results for 5 minutes in state_manager and local memory.
        """
        try:
            now = time.time()
            # check local cache first
            cache = self.state.get_chain_perf_cache() or {"data": {}, "timestamp": 0}
            if now - cache.get("timestamp", 0) < self._local_chain_cache_ttl:
                return cache.get("data", {})

            headers = {"X-API-Key": MORALIS_API_KEY} if MORALIS_API_KEY else {}
            results = {}

            for chain in chains:
                perf = None
                # Try Moralis if key present
                if MORALIS_API_KEY:
                    try:
                        # Note: Moralis endpoints may differ by plan; user free plan may restrict. This is a best-effort call.
                        url = f"https://deep-index.moralis.io/api/v2/market/{chain}/summary"
                        # fallback: some Moralis deployments use /market-data/{chain}/summary - handle both
                        r = requests.get(url, headers=headers, timeout=10)
                        if r.status_code == 200:
                            j = r.json()
                            # try common keys
                            perf = j.get("priceChange24h") or j.get("price_change_percentage_24h")
                    except Exception:
                        logging.debug(f"Moralis primary url failed for {chain}, trying alternate")
                        try:
                            url2 = f"https://deep-index.moralis.io/api/v2/market-data/{chain}/summary"
                            r2 = requests.get(url2, headers=headers, timeout=10)
                            if r2.status_code == 200:
                                j2 = r2.json()
                                perf = j2.get("priceChange24h") or j2.get("price_change_percentage_24h")
                        except Exception as e2:
                            logging.warning(f"Moralis alternate failed for {chain}: {e2}")

                if perf is None:
                    # CoinGecko fallback - try to map chain id to a CoinGecko coin id
                    try:
                        # For chain-level fallback, pick representative coin mapping
                        mapping = {
                            "ethereum": "ethereum",
                            "solana": "solana",
                            "base": "base",            # base is relatively new on coingecko
                            "bnb": "binancecoin",
                            "arbitrum": "arbitrum",
                            "optimism": "optimism",
                            "polygon": "polygon",
                            "avalanche": "avalanche-2"
                        }
                        cg_id = mapping.get(chain.lower(), chain.lower())
                        r = requests.get(f"{COINGECKO_API_BASE}/coins/{cg_id}", timeout=10)
                        if r.status_code == 200:
                            j = r.json()
                            perf = j.get("market_data", {}).get("price_change_percentage_24h")
                    except Exception as e:
                        logging.warning(f"CoinGecko fallback failed for {chain}: {e}")

                if perf is None:
                    logging.warning(f"No perf data for chain {chain}. Setting to 0.0")
                    perf = 0.0
                # ensure float
                try:
                    perf = float(perf)
                except Exception:
                    perf = 0.0
                results[chain] = perf

            # update cache in state manager
            self.state.update_chain_perf_cache(results, now)
            return results
        except Exception as e:
            logging.error(f"get_chain_performance unexpected error: {e}")
            return {}

    # ------------------------
    # Build market snapshot for a symbol
    # ------------------------
    def build_market_snapshot(self, symbol: str) -> dict:
        """
        Returns a snapshot dict for given symbol (e.g., 'BTC', 'ETH', 'SOL', etc.)
        keys: price, price_change_24h, volume_24h, fear_greed, orderbook_bias, chain (if applicable), news (titles)
        """
        s = {
            "symbol": symbol,
            "price": None,
            "price_change_24h": None,
            "volume_24h": None,
            "fear_greed_value": None,
            "fear_greed_sentiment": None,
            "orderbook_bias": "unknown",
            "chain": None,
            "news": []
        }
        try:
            # 1) current price & 24h change via CoinGecko simple endpoint (fast)
            try:
                # try coin id mapping by symbol -> use search endpoint
                r = requests.get(f"{COINGECKO_API_BASE}/search?query={symbol}", timeout=8)
                cg_id = None
                if r.status_code == 200:
                    j = r.json()
                    coins = j.get("coins", [])
                    # prefer exact symbol match
                    for c in coins:
                        if c.get("symbol", "").upper() == symbol.upper():
                            cg_id = c.get("id")
                            break
                    if not cg_id and coins:
                        cg_id = coins[0].get("id")
                if cg_id:
                    r2 = requests.get(f"{COINGECKO_API_BASE}/coins/{cg_id}", timeout=8)
                    if r2.status_code == 200:
                        j2 = r2.json()
                        md = j2.get("market_data", {})
                        s["price"] = md.get("current_price", {}).get("usd")
                        s["price_change_24h"] = md.get("price_change_percentage_24h")
                        s["volume_24h"] = md.get("total_volume", {}).get("usd")
                        # chain inference
                        platforms = j2.get("platforms", {})
                        if platforms:
                            # take first platform key as chain
                            first_chain = next(iter(platforms.keys()))
                            s["chain"] = first_chain
                else:
                    logging.debug(f"CoinGecko search returned no id for {symbol}")
            except Exception as e:
                logging.warning(f"CoinGecko price fetch failed for {symbol}: {e}")

            # 2) Fear & Greed
            fg_val, fg_sent = self.get_fear_and_greed_index()
            s["fear_greed_value"] = fg_val
            s["fear_greed_sentiment"] = fg_sent

            # 3) Orderbook bias (best effort): try public CCXT exchange (no auth) -> use bitget/binance etc
            try:
                exch_name = os.getenv("MARKET_ORDERBOOK_EXCHANGE", "binance")
                exchange_class = getattr(ccxt, exch_name)
                ex = exchange_class()
                # build a ticker symbol for exchange: try typical forms
                ticker_candidates = [f"{symbol}/USDT", f"{symbol}/USD", f"{symbol}/BTC"]
                ob = None
                for t in ticker_candidates:
                    try:
                        if t in ex.markets:
                            ob = ex.fetch_order_book(t)
                            break
                    except Exception:
                        # try to load markets then fetch
                        try:
                            ex.load_markets()
                            if t in ex.markets:
                                ob = ex.fetch_order_book(t)
                                break
                        except Exception:
                            continue
                if ob:
                    bids = ob.get("bids", [])
                    asks = ob.get("asks", [])
                    bid_depth = sum([b[1] for b in bids[:10]]) if bids else 0.0
                    ask_depth = sum([a[1] for a in asks[:10]]) if asks else 0.0
                    if bid_depth + ask_depth > 0:
                        bias_percent = (bid_depth - ask_depth) / (bid_depth + ask_depth) * 100
                        if bias_percent > 5:
                            s["orderbook_bias"] = "buy-heavy"
                        elif bias_percent < -5:
                            s["orderbook_bias"] = "sell-heavy"
                        else:
                            s["orderbook_bias"] = "balanced"
                else:
                    s["orderbook_bias"] = "unknown"
            except Exception as e:
                logging.debug(f"Orderbook fetch attempt failed: {e}")
                s["orderbook_bias"] = "unknown"

            # 4) News headlines (English + Japanese sources) - combine: NewsAPI + some Japanese sources fallback
            s["news"] = self._fetch_news_headlines(symbol, max_items=5)

        except Exception as e:
            logging.error(f"build_market_snapshot error for {symbol}: {e}")

        return s

    def _fetch_news_headlines(self, symbol: str, max_items=5):
        """
        Best-effort headlines:
         - Primary: NewsAPI (if API key provided in env NEWSAPI_KEY)
         - Fallback: Cointelegraph / Coindesk scraping (limited)
         - Also try to fetch some Japanese headlines via CoinPost/CryptoTimes if possible
        Returns list of strings (title strings). Keeps to English + Japanese where available.
        """
        headlines = []
        NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
        try:
            if NEWSAPI_KEY:
                q = f"{symbol} OR crypto OR blockchain"
                url = f"https://newsapi.org/v2/everything?q={requests.utils.quote(q)}&pageSize={max_items}&language=en&apiKey={NEWSAPI_KEY}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    j = r.json()
                    for art in j.get("articles", [])[:max_items]:
                        headlines.append(art.get("title"))
            # Japanese sources (simple fetch of latest headlines from known sites)
            if len(headlines) < max_items:
                try:
                    # example: coinpost.jp feed (if accessible)
                    rj = requests.get("https://coinpost.jp/", timeout=8)
                    if rj.status_code == 200:
                        # naive extraction: find <title> tags - keep small fallback
                        import re
                        titles = re.findall(r"<h2.*?>([^<]{10,200})</h2>", rj.text, flags=re.I|re.S)
                        for t in titles:
                            if len(headlines) >= max_items: break
                            headlines.append(t.strip())
                except Exception:
                    pass
        except Exception as e:
            logging.debug(f"News fetch error: {e}")

        # Ensure uniqueness and limit
        uniq = []
        for h in headlines:
            if h and h not in uniq:
                uniq.append(h)
            if len(uniq) >= max_items:
                break
        return uniq

    # ------------------------
    # AI trade proposal via OpenAI
    # ------------------------
    def get_ai_trade_proposal(self, symbol: str, snapshot: dict, position: dict = None, priority: bool = False, max_tokens=400) -> str:
        """
        Compose a prompt and call OpenAI ChatCompletion to get a trade-oriented suggestion in Japanese.
        If OPENAI_API_KEY not set, returns a short heuristic string.
        - priority True means the symbol is currently held -> request more detailed output
        """
        try:
            # build prompt
            header = "あなたはプロの仮想通貨トレーダーで、初心者にも分かりやすく提案する日本語アシスタントです。"
            if position and priority:
                role_desc = (
                    f"以下は保有ポジションの情報です。保有中の銘柄について、"
                    "初心者でもわかる丁寧な日本語で、できるだけ具体的に「推奨アクション（利確/損切/保有継続）」「利確価格」「損切価格」「残高に与える概算影響（USD）」"
                    "を数字を含めて提示してください。理由も簡潔に述べてください。"
                )
            else:
                role_desc = (
                    "保有していない銘柄について、初心者にも分かりやすく「推奨アクション（買い/売り/様子見）」「利確の参考値」「損切の参考値」を挙げてください。"
                )

            # snapshot summarization
            snap_lines = []
            snap_lines.append(f"銘柄: {symbol}")
            p = snapshot.get("price")
            snap_lines.append(f"現在価格(USD): {p if p is not None else 'N/A'}")
            pc24 = snapshot.get("price_change_24h")
            snap_lines.append(f"24h変動(%) : {pc24 if pc24 is not None else 'N/A'}")
            snap_lines.append(f"24h出来高(USD): {snapshot.get('volume_24h', 'N/A')}")
            fg = snapshot.get("fear_greed_value")
            snap_lines.append(f"Fear&Greed: {fg} ({snapshot.get('fear_greed_sentiment')})")
            snap_lines.append(f"板の厚み: {snapshot.get('orderbook_bias')}")
            if position:
                snap_lines.append(f"ポジション: {position}")
            news = snapshot.get("news", [])
            if news:
                snap_lines.append("最新ニュース見出し:")
                for n in news[:3]:
                    snap_lines.append(f"- {n}")

            prompt = f"{header}\n\n{role_desc}\n\nデータ:\n" + "\n".join(snap_lines) + "\n\n出力形式:\n1) 日本語のやさしい説明（短く）\n2) 推奨アクション: <買い/売り/様子見/利確/損切> とその理由\n3) 利確 (USD 値) / 損切 (USD 値)（もし計算できるなら具体的な数値）\n4) 残高やポジションに対する想定損益（簡単な概算）\n\n注意: 初心者向けに易しく書いてください。"

            if not OPENAI_API_KEY:
                # fallback heuristic mini-message
                if p is None:
                    return f"{symbol}: データ不足のため提案できません。"
                # simple rules
                if pc24 and pc24 > 10:
                    return f"{symbol}: 買い候補。短期利確を検討。利確: {round(p * 1.05, 2)} USD / 損切: {round(p * 0.98, 2)} USD"
                elif pc24 and pc24 < -8:
                    return f"{symbol}: 売り（ショート）候補。利確: {round(p * 0.97, 2)} USD / 損切: {round(p * 1.02, 2)} USD"
                else:
                    return f"{symbol}: 様子見。方向感がはっきりしないため、大きなポジションは控えてください。"

            # Call OpenAI (ChatCompletion)
            # Use ChatCompletion API; models may vary by availability
            try:
                # rate-limiting small sleep to avoid hitting OpenAI too quickly when multiple symbols
                time.sleep(0.3)
                resp = openai.ChatCompletion.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": header},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.6,
                )
                text = resp["choices"][0]["message"]["content"].strip()
                # optionally update cache in state manager
                try:
                    self.state.update_ai_comment(symbol, text)
                except Exception:
                    pass
                return text
            except Exception as e:
                logging.error(f"OpenAI call failed for {symbol}: {e}")
                # fallback short string
                return f"{symbol}: AI生成に失敗しました ({e})"

        except Exception as e:
            logging.error(f"get_ai_trade_proposal error: {e}")
            return f"{symbol}: 内部エラーで提案不可"

