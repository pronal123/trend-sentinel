# sentiment_analyzer.py
import requests
import logging
import time
from utils import api_retry_decorator

class SentimentAnalyzer:
    """
    市場のセンチメント（心理状況）を分析するクラス。
    """
    def __init__(self):
        self.fng_url = "https://api.alternative.me/fng/?limit=1"

    @api_retry_decorator(retries=3, delay=3)
    def get_fear_and_greed_index(self):
        """
        キャッシュを回避して、常に最新のFear & Greed Indexを取得する。
        戻り値: {'value': (0-100), 'sentiment': "Fear"など} or None
        """
        try:
            # URLに現在のタイムスタンプ（Unix時間）を追加して、キャッシュを無効化する
            cache_busting_url = f"{self.fng_url}&timestamp={int(time.time())}"
            
            response = requests.get(cache_busting_url, timeout=10)
            response.raise_for_status() # HTTPエラーがあれば例外を発生させる
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
        except (KeyError, IndexError) as e:
            logging.error(f"Failed to parse Fear & Greed Index API response: {e}")
            return None
