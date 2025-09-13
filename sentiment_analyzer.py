# sentiment_analyzer.py
import requests
import logging

class SentimentAnalyzer:
    def __init__(self):
        self.fng_url = "https://api.alternative.me/fng/?limit=1"

    def get_fear_and_greed_index(self):
        """
        Alternative.meからCrypto Fear & Greed Indexを取得する。
        戻り値: {'value': (0-100), 'sentiment': "Fear"など} or None
        """
        try:
            response = requests.get(self.fng_url, timeout=10)
            response.raise_for_status() # エラーがあれば例外を発生
            data = response.json()['data'][0]
            
            fng_data = {
                'value': int(data['value']),
                'sentiment': data['value_classification']
            }
            logging.info(f"Successfully fetched Fear & Greed Index: {fng_data['value']} ({fng_data['sentiment']})")
            return fng_data
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch Fear & Greed Index: {e}")
            return None
