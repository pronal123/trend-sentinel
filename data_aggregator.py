# data_aggregator.py
import os
import logging
import pandas as pd
from pycoingecko import CoinGeckoAPI
import requests # CryptoCompare APIのために追加

class DataAggregator:
    def __init__(self):
        self.cg = CoinGeckoAPI()
        # APIキーを環境変数から読み込む
        self.moralis_api_key = os.environ.get("MORALIS_API_KEY")
        self.cryptocompare_api_key = os.environ.get("CRYPTOCOMPARE_API_KEY")

    def get_onchain_data(self, token_symbol):
        """Moralisから主要なオンチェーンデータを取得する"""
        if not self.moralis_api_key: return None
        logging.info(f"Fetching on-chain data for {token_symbol}...")
        try:
            # ここではダミーデータを返しますが、実際にはMoralis APIを呼び出します
            # 例：アクティブアドレス数、大口ウォレットの動き、取引量など
            return {
                'active_addresses_24h_change': 15.5, # アクティブアドレス変化率(%)
                'whale_transaction_volume': 5200000, # 大口取引量($)
            }
        except Exception as e:
            logging.error(f"Failed to fetch on-chain data for {token_symbol}: {e}")
            return None

    def get_sentiment_data(self, token_symbol):
        """CryptoCompareからニュースやSNSのセンチメントを取得する"""
        if not self.cryptocompare_api_key: return None
        logging.info(f"Fetching sentiment data for {token_symbol}...")
        try:
            # CryptoCompare APIのエンドポイント (例)
            # url = f"https://min-api.cryptocompare.com/data/v2/news/?categories={token_symbol}&api_key={self.cryptocompare_api_key}"
            # response = requests.get(url).json()
            # ここではダミーデータを返します
            return {
                'news_sentiment_score': 72.8, # ニュースセンチメントスコア (0-100)
                'twitter_followers_change_24h': 2.1 # Twitterフォロワー変化率 (%)
            }
        except Exception as e:
            logging.error(f"Failed to fetch sentiment data for {token_symbol}: {e}")
            return None

    def get_enriched_market_data(self):
        """価格、オンチェーン、センチメントを統合したデータを生成する"""
        # 1. CoinGeckoから基本市場データを取得
        base_data = self.get_top_tokens() # 上位銘柄を取得する関数 (既存)
        enriched_rows = []

        for token in base_data:
            token_symbol = token['symbol'].upper()
            
            # 2. オンチェーンデータを取得
            onchain_stats = self.get_onchain_data(token_symbol)
            if onchain_stats:
                token.update(onchain_stats)
            
            # 3. センチメントデータを取得
            sentiment_stats = self.get_sentiment_data(token_symbol)
            if sentiment_stats:
                token.update(sentiment_stats)
            
            enriched_rows.append(token)
            
        return pd.DataFrame(enriched_rows)
