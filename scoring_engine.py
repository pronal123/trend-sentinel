# scoring_engine.py
import logging
# ... (他のインポート)

class ScoringEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        # 新しい評価項目を追加し、ウェイトを調整 (合計100)
        self.WEIGHTS = {
            'technical': 30,
            'trend': 20,
            'onchain': 25,     # <--- 追加
            'sentiment': 15,   # <--- sentimentから名称変更
            'order_book': 10,
        }
    
    # ... (score_technical, score_trend, score_order_bookは前回と同様)

    def score_onchain(self, token_data):
        """オンチェーンデータの健全性をスコア化する"""
        score = 0
        max_score = self.WEIGHTS['onchain']
        
        # アクティブアドレスが増加していれば高評価
        if token_data.get('active_addresses_24h_change', 0) > 10:
            score += max_score * 0.6
        
        # 大口の買いが観測されれば高評価
        if token_data.get('whale_transaction_volume', 0) > 1000000:
            score += max_score * 0.4
            
        return score

    def score_sentiment(self, token_data):
        """市場心理（センチメント）をスコア化する"""
        score = 0
        max_score = self.WEIGHTS['sentiment']

        # ニュースのセンチメントスコアが高ければ高評価
        if token_data.get('news_sentiment_score', 50) > 65:
            score += max_score * 0.7
            
        # SNSでの注目度（フォロワー）が上がっていれば高評価
        if token_data.get('twitter_followers_change_24h', 0) > 1.5:
            score += max_score * 0.3
            
        return score

    def calculate_total_score(self, token_data, series):
        """全項目を評価し、総合得点を算出する"""
        # ... (既存のスコア計算)
        
        # 新しいスコア計算を追加
        onchain_score = self.score_onchain(token_data)
        sentiment_score = self.score_sentiment(token_data)
        
        total_score = tech_score + trend_score + onchain_score + sentiment_score + order_book_score
        
        logging.info(f"Scoring for {token_data['symbol']}: Tech={tech_score:.1f}, Trend={trend_score:.1f}, OnChain={onchain_score:.1f}, Sentiment={sentiment_score:.1f}, OrderBook={order_book_score:.1f} | TOTAL={total_score:.1f}")
        
        return total_score
