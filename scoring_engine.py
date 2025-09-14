# scoring_engine.py
import logging
import pandas as pd
import pandas_ta as ta
import yfinance as yf

class ScoringEngine:
    """
    市場の多角的分析とスコアリングを担当する。
    市場レジームに応じて分析ウェイトを動的に変更し、分析コメントを生成する。
    """
    def __init__(self, exchange):
        self.exchange = exchange
        # レジーム別のウェイトを定義
        self.WEIGHTS_TRENDING = {
            'technical': 25, 'trend': 35, 'onchain': 25, 
            'sentiment': 5, 'order_book': 10
        }
        self.WEIGHTS_RANGING = {
            'technical': 35, 'trend': 5, 'onchain': 10, 
            'sentiment': 25, 'order_book': 25
        }

    def calculate_total_score(self, token_data, yf_ticker, fng_data, regime):
        """全項目を評価し、総合得点と分析コメントを返す"""
        try:
            series = yf.download(yf_ticker, period='1y', progress=False)
            if series.empty or 'Close' not in series.columns:
                return 0, None, "分析対象の市場データ取得に失敗、またはデータが不完全です。"

            weights = self.WEIGHTS_TRENDING if regime == 'TRENDING' else self.WEIGHTS_RANGING
            
            tech_score, tech_comment = self._score_technical(series, weights['technical'])
            trend_score, trend_comment = self._score_trend(series, weights['trend'])
            onchain_score, onchain_comment = self._score_onchain(token_data, weights['onchain'])
            sentiment_score, sentiment_comment = self._score_sentiment(fng_data, token_data, weights['sentiment'])
            order_book_score, order_book_comment = self._score_order_book(f"{token_data.get('symbol', '').upper()}/USDT", weights['order_book'])
            
            total_score = tech_score + trend_score + onchain_score + sentiment_score + order_book_score
            
            analysis_comments = (
                f"{tech_comment}\n\n"
                f"{trend_comment}\n\n"
                f"{onchain_comment}\n\n"
                f"{sentiment_comment}\n\n"
                f"{order_book_comment}"
            )
            
            logging.info(f"Scoring for {yf_ticker}: TOTAL={total_score:.1f} (Regime: {regime})")
            return total_score, series, analysis_comments

        except Exception as e:
            logging.error(f"Error during score calculation for {yf_ticker}: {e}")
            return 0, None, f"分析中に予期せぬエラーが発生しました: {e}"

    def _score_technical(self, series, max_score):
        score, comments = 0, []
        try:
            if not all(k in series.columns for k in ['open', 'high', 'low', 'close']):
                raise ValueError("OHLC data is missing for technical analysis.")

            rsi = series.ta.rsi().iloc[-1]
            macd = series.ta.macd().iloc[-1]
            if 30 < rsi < 65:
                score += max_score * 0.5; comments.append(f"RSI({rsi:.1f})は中立圏。")
            else: comments.append(f"RSI({rsi:.1f})は過熱/売られすぎ圏内。")

            if macd['MACD_12_26_9'] > macd['MACDs_12_26_9']:
                score += max_score * 0.5; comments.append("MACDはゴールデンクロス中。")
            else: comments.append("MACDはデッドクロス中。")
        except Exception as e:
            comments.append(f"テクニカル指標の計算に失敗: {e}")
        
        return score, f"📈 テクニカル ({score:.1f}/{max_score}点)\n{' '.join(comments)}"

    def _score_trend(self, series, max_score):
        try:
            if 'close' not in series.columns or len(series) < 200:
                 raise ValueError("Not enough data for trend analysis.")
            sma50 = series.ta.sma(50).iloc[-1]
            sma200 = series.ta.sma(200).iloc[-1]
            if sma50 > sma200:
                return max_score, f"📊 トレンド ({max_score}/{max_score}点)\n長期上昇トレンド（50日MA > 200日MA）。"
            else:
                return 0, f"📊 トレンド (0/{max_score}点)\n長期下降トレンド（50日MA < 200日MA）。"
        except Exception as e:
            return 0, f"📊 トレンド (0/{max_score}点)\nトレンドを判断できませんでした: {e}"

    def _score_onchain(self, token_data, max_score):
        score, comments = 0, []
        # ダミーデータに基づくコメント
        if token_data.get('active_addresses_24h_change', 0) > 10:
            score += max_score * 0.6; comments.append("ネットワーク活動が活発化。")
        else: comments.append("ネットワーク活動は停滞気味。")
        if token_data.get('whale_transaction_volume', 0) > 1000000:
            score += max_score * 0.4; comments.append("大口投資家の取引が観測。")
        
        comment_text = '\n'.join(comments) if comments else "オンチェーンデータが不足。"
        return score, f"🔗 オンチェーン ({score:.1f}/{max_score}点)\n{comment_text}"

    def _score_sentiment(self, fng_data, token_data, max_score):
        score, comments = 0, []
        if fng_data:
            score += (100 - fng_data['value']) / 100 * max_score * 0.5
            comments.append(f"市場心理は「{fng_data['sentiment']}」(指数:{fng_data['value']})。")
        if token_data.get('news_sentiment_score', 50) > 65:
            score += max_score * 0.5; comments.append("関連ニュースはポジティブ傾向。")
            
        comment_text = '\n'.join(comments) if comments else "センチメントを判断できませんでした。"
        return score, f"🧠 センチメント ({score:.1f}/{max_score}点)\n{comment_text}"

    def _score_order_book(self, ticker, max_score):
        if not self.exchange: return 0, f"📚 オーダーブック (0/{max_score}点)\n取引所未接続。"
        try:
            order_book = self.exchange.fetch_l2_order_book(ticker, limit=10)
            bids_vol = sum([size for _, size in order_book['bids']])
            asks_vol = sum([size for _, size in order_book['asks']])
            if (bids_vol + asks_vol) == 0: return 0, f"📚 オーダーブック (0/{max_score}点)\n板情報が非常に薄い。"
            buy_pressure = bids_vol / (bids_vol + asks_vol)
            score = buy_pressure * max_score
            comment = f"直近の板では買い圧力が{(buy_pressure*100):.1f}%を占有。"
            return score, f"📚 オーダーブック ({score:.1f}/{max_score}点)\n{comment}"
        except Exception as e:
            return 0, f"📚 オーダーブック (0/{max_score}点)\n板情報を取得できませんでした: {e}"
