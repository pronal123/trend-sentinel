# scoring_engine.py
import logging
import pandas_ta as ta

class ScoringEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        self.WEIGHTS = {
            'technical': 35, 'trend': 25, 
            'sentiment': 20, # 市場心理
            'order_book': 20
        }

    def _score_sentiment(self, fng_data):
        """市場心理（恐怖と強欲指数）をスコア化する"""
        if not fng_data:
            return self.WEIGHTS['sentiment'] / 2 # データ取得失敗時は中間点

        # 逆張り戦略：市場が恐怖に包まれているほど、買いの好機と判断
        # (100 - 恐怖指数) でスコアを算出
        score = (100 - fng_data['value']) / 100 * self.WEIGHTS['sentiment']
        return score

    def calculate_total_score(self, ticker, series, fng_data):
        """全項目を評価し、総合得点を算出する"""
        tech_score = self._score_technical(series)
        trend_score = self._score_trend(series)
        sentiment_score = self._score_sentiment(fng_data)
        order_book_score = self._score_order_book(ticker)
        
        total_score = tech_score + trend_score + sentiment_score + order_book_score
        
        logging.info(
            f"Scoring for {ticker}: Tech={tech_score:.1f}, Trend={trend_score:.1f}, "
            f"Sentiment={sentiment_score:.1f}, OrderBook={order_book_score:.1f} | TOTAL={total_score:.1f}"
        )
        return total_score
    
    # ... (_score_technical, _score_trend, _score_order_book は変更なし)
