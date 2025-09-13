# scoring_engine.py
import logging
import pandas as pd
import pandas_ta as ta

class ScoringEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        self.WEIGHTS = {'technical': 35, 'trend': 25, 'sentiment': 20, 'order_book': 20}

    def _get_historical_data(self, ticker, period='1y'):
        # 実際のデータ取得はdata_aggregatorに任せるべきだが、ここでは簡易的に実装
        from yfinance import download
        return download(ticker, period=period)

    def calculate_total_score(self, ticker_id, yf_ticker):
        """指定された銘柄の総合得点を計算する"""
        try:
            series = self._get_historical_data(yf_ticker)
            if series.empty: return 0

            tech_score = self._score_technical(series)
            trend_score = self._score_trend(series)
            sentiment_score = self._score_sentiment()
            order_book_score = self._score_order_book(f"{yf_ticker.split('-')[0]}/USD") # 例: BTC/USD
            
            total_score = tech_score + trend_score + sentiment_score + order_book_score
            logging.info(f"Scoring for {yf_ticker}: Tech={tech_score:.1f}, Trend={trend_score:.1f}, Sentiment={sentiment_score:.1f}, OrderBook={order_book_score:.1f} | TOTAL={total_score:.1f}")
            return total_score, series
        except Exception as e:
            logging.error(f"Failed to calculate score for {yf_ticker}: {e}")
            return 0, None

    def _score_technical(self, series):
        score = 0
        rsi = series.ta.rsi().iloc[-1]
        if 30 < rsi < 65: score += self.WEIGHTS['technical'] * 0.5
        
        macd = series.ta.macd().iloc[-1]
        if macd['MACD_12_26_9'] > macd['MACDs_12_26_9']: score += self.WEIGHTS['technical'] * 0.5
        return score

    def _score_trend(self, series):
        sma50 = series.ta.sma(50).iloc[-1]
        sma200 = series.ta.sma(200).iloc[-1]
        return self.WEIGHTS['trend'] if sma50 > sma200 else 0

    def _score_sentiment(self):
        # 外部API（Fear & Greed Index等）を利用する
        fear_and_greed = 30 # ダミーデータ (恐怖状態)
        return (100 - fear_and_greed) / 100 * self.WEIGHTS['sentiment']

    def _score_order_book(self, ticker):
        if not self.exchange: return 0
        try:
            order_book = self.exchange.fetch_l2_order_book(ticker)
            bids = sum([size for _, size in order_book['bids'][:10]])
            asks = sum([size for _, size in order_book['asks'][:10]])
            buy_pressure = bids / (bids + asks)
            return buy_pressure * self.WEIGHTS['order_book']
        except Exception:
            return 0
