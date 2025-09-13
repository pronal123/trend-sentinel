# scoring_engine.py
import logging
import pandas as pd
import pandas_ta as ta
# yfinanceはdata_aggregatorに集約するのが望ましいが、ここでは簡易的に使用
import yfinance as yf

class ScoringEngine:
    """
    市場の多角的分析とスコアリングを担当する。
    市場レジームに応じて分析ウェイトを動的に変更する。
    """
    def __init__(self, exchange):
        self.exchange = exchange
        # --- レジーム別のウェイトを定義 (合計100) ---
        # トレンド相場では、トレンド追随の指標を重視
        self.WEIGHTS_TRENDING = {
            'technical': 25, 'trend': 35, 'onchain': 25, 
            'sentiment': 5, 'order_book': 10
        }
        # レンジ相場では、逆張りと短期的な需給を重視
        self.WEIGHTS_RANGING = {
            'technical': 35, 'trend': 5, 'onchain': 10, 
            'sentiment': 25, 'order_book': 25
        }

    def calculate_total_score(self, token_data, yf_ticker, fng_data, regime):
        """全項目を評価し、総合得点を算出。レジームに応じてウェイトを変更"""
        try:
            series = yf.download(yf_ticker, period='1y')
            if series.empty: return 0, None

            # 現在のレジームに応じて使用するウェイトを選択
            weights = self.WEIGHTS_TRENDING if regime == 'TRENDING' else self.WEIGHTS_RANGING
            logging.info(f"Using scoring weights for {regime} regime for {yf_ticker}.")

            # 各項目をスコア化
            tech_score = self._score_technical(series, weights['technical'])
            trend_score = self._score_trend(series, weights['trend'])
            onchain_score = self._score_onchain(token_data, weights['onchain'])
            sentiment_score = self._score_sentiment(fng_data, token_data, weights['sentiment'])
            order_book_score = self._score_order_book(f"{token_data['symbol'].upper()}/USDT", weights['order_book'])
            
            total_score = tech_score + trend_score + onchain_score + sentiment_score + order_book_score
            
            logging.info(f"Scoring for {yf_ticker}: Tech={tech_score:.1f}, Trend={trend_score:.1f}, OnChain={onchain_score:.1f}, Sentiment={sentiment_score:.1f}, OrderBook={order_book_score:.1f} | TOTAL={total_score:.1f}")
            
            return total_score, series
        except Exception as e:
            logging.error(f"Failed to calculate score for {yf_ticker}: {e}")
            return 0, None

    def _score_technical(self, series, max_score):
        """チャートのテクニカル指標をスコア化する"""
        score = 0
        try:
            rsi = series.ta.rsi().iloc[-1]
            if 30 < rsi < 65: score += max_score * 0.5
            
            macd = series.ta.macd().iloc[-1]
            if macd['MACD_12_26_9'] > macd['MACDs_12_26_9']: score += max_score * 0.5
        except Exception: pass
        return score

    def _score_trend(self, series, max_score):
        """トレンドの強さをスコア化する"""
        try:
            sma50 = series.ta.sma(50).iloc[-1]
            sma200 = series.ta.sma(200).iloc[-1]
            return max_score if sma50 > sma200 else 0
        except Exception: return 0

    def _score_onchain(self, token_data, max_score):
        """オンチェーンデータの健全性をスコア化する"""
        score = 0
        if token_data.get('active_addresses_24h_change', 0) > 10: score += max_score * 0.6
        if token_data.get('whale_transaction_volume', 0) > 1000000: score += max_score * 0.4
        return score

    def _score_sentiment(self, fng_data, token_data, max_score):
        """市場心理（センチメント）をスコア化する"""
        score = 0
        if fng_data:
            # 逆張り指標：市場が恐怖なら高スコア
            score += (100 - fng_data['value']) / 100 * max_score * 0.5
        if token_data.get('news_sentiment_score', 50) > 65:
            score += max_score * 0.5
        return score

    def _score_order_book(self, ticker, max_score):
        """取引板の厚みをスコア化する"""
        if not self.exchange: return 0
        try:
            order_book = self.exchange.fetch_l2_order_book(ticker)
            bids_vol = sum([size for _, size in order_book['bids'][:10]])
            asks_vol = sum([size for _, size in order_book['asks'][:10]])
            
            if (bids_vol + asks_vol) == 0: return 0
            
            buy_pressure = bids_vol / (bids_vol + asks_vol)
            return buy_pressure * max_score
        except Exception:
            return 0
