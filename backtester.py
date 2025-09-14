import yfinance as yf
import pandas as pd
import logging
import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from data_aggregator import DataAggregator

load_dotenv()


class Backtester:
    def __init__(self, interval="5m", period="30d", state_file="bot_state.json", cache_file="trending_cache.json"):
        self.interval = interval
        self.period = period
        self.aggregator = DataAggregator()
        self.state_file = state_file
        self.cache_file = cache_file
        self.coingecko_key = os.getenv("COINGECKO_API_KEY")

    # --- トレンドキャッシュを管理 ---
    def _load_trending_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r") as f:
                return json.load(f)
        return []

    def _save_trending_cache(self, data):
        with open(self.cache_file, "w") as f:
            json.dump(data, f, indent=2)

    # --- 動的銘柄リスト生成 ---
    def get_dynamic_symbols(self):
        symbols = set()
        now = datetime.utcnow()
        trending_cache = self._load_trending_cache()

        # Coingecko トレンド銘柄（TOP7）
        try:
            url = "https://api.coingecko.com/api/v3/search/trending"
            headers = {"accept": "application/json"}
            if self.coingecko_key:
                headers["x-cg-pro-api-key"] = self.coingecko_key
            res = requests.get(url, headers=headers, timeout=10).json()

            new_entries = []
            for item in res.get("coins", []):
                symbol = item["item"]["symbol"].upper()
                symbol_full = f"{symbol}-USD"
                symbols.add(symbol_full)
                new_entries.append({"symbol": symbol_full, "time": now.isoformat()})

            # キャッシュに追加
            trending_cache.extend(new_entries)

        except Exception as e:
            logging.error(f"Coingecko fetch error: {e}")

        # 24時間以内の履歴を残す
        cutoff = now - timedelta(hours=24)
        trending_cache = [entry for entry in trending_cache if datetime.fromisoformat(entry["time"]) >= cutoff]
        self._save_trending_cache(trending_cache)

        # 24h 履歴を追加
        for entry in trending_cache:
            symbols.add(entry["symbol"])

        # 保有ポジション銘柄（state_manager 管理）
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
                positions = state.get("positions", {})
                for sym in positions.keys():
                    symbols.add(f"{sym}-USD")
        except Exception as e:
            logging.warning(f"Could not load state file: {e}")

        # デフォルト主要銘柄
        default = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]
        symbols.update(default)

        logging.info(f"Dynamic backtest symbols: {symbols}")
        return list(symbols)

    # --- バックテスト実行（省略: 前バージョンと同じ） ---
    def run_backtest_for_symbol(self, symbol):
        # （ここは前回のコードと同じ処理）
        ...
