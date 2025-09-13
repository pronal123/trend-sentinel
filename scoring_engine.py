# scoring_engine.py
import logging
import pandas_ta as ta

class ScoringEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        # 各評価項目の最大スコアを定義 (合計100)
        self.WEIGHTS = {
            'technical': 35,
            'trend': 25,
            'sentiment': 20,
            'order_book': 20,
        }

    def score_technical(self, series):
        """チャートのテクニカル指標をスコア化する"""
        score = 0
        max_score = self.WEIGHTS['technical']
        
        rsi = series.ta.rsi().iloc[-1]
        macd = series.ta.macd().iloc[-1]
        
        if 30 < rsi < 60: score += max_score * 0.4 # 買われすぎでも売られすぎでもない
        if macd['MACD_12_26_9'] > macd['MACDs_12_26_9']: score += max_score * 0.6 # MACDがシグナルを上回る (ゴールデンクロス)
        
        return score

    def score_trend(self, series):
        """トレンドの強さをスコア化する"""
        score = 0
        max_score = self.WEIGHTS['trend']
        
        # 50日移動平均線が200日移動平均線を上回っていれば強い上昇トレンド
        sma50 = series.ta.sma(50).iloc[-1]
        sma200 = series.ta.sma(200).iloc[-1]
        
        if sma50 > sma200: score += max_score
        
        return score

    def score_sentiment(self):
        """市場心理（恐怖と強欲指数など）をスコア化する"""
        # TODO: Fear & Greed Index APIなどを呼び出す
        # 例: fear_and_greed_index = 25 (Extreme Fear)
        # 逆張り戦略として、恐怖が強いほど買いのチャンスと判断
        fear_and_greed_index = 25 # ダミーデータ
        score = (100 - fear_and_greed_index) / 100 * self.WEIGHTS['sentiment']
        return score
        
    def score_order_book(self, ticker):
        """取引板の厚みをスコア化する"""
        if not self.exchange: return 0
        try:
            # 注文板情報を取得
            order_book = self.exchange.fetch_l2_order_book(ticker)
            bids = sum([price * size for price, size in order_book['bids'][:10]]) # 上位10件の買い注文総額
            asks = sum([price * size for price, size in order_book['asks'][:10]]) # 上位10件の売り注文総額
            
            if (bids + asks) == 0: return 0
            
            # 買い圧力の割合をスコア化
            buy_pressure_ratio = bids / (bids + asks)
            return buy_pressure_ratio * self.WEIGHTS['order_book']
            
        except Exception as e:
            logging.warning(f"Could not fetch order book for {ticker}: {e}")
            return 0

    def calculate_total_score(self, ticker, series):
        """全項目を評価し、総合得点を算出する"""
        tech_score = self.score_technical(series)
        trend_score = self.score_trend(series)
        sentiment_score = self.score_sentiment()
        order_book_score = self.score_order_book(ticker)
        
        total_score = tech_score + trend_score + sentiment_score + order_book_score
        
        logging.info(f"Scoring for {ticker}: Tech={tech_score:.1f}, Trend={trend_score:.1f}, Sentiment={sentiment_score:.1f}, OrderBook={order_book_score:.1f} | TOTAL={total_score:.1f}")
        
        return total_score
