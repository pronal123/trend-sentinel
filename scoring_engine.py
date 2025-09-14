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
            'technical': 25, 'trend': 35, 'sentiment': 15, 'order_book': 25
        }
        self.WEIGHTS_RANGING = {
            'technical': 35, 'trend': 5, 'sentiment': 25, 'order_book': 35
        }

    def calculate_total_score(self, token_data, series, fng_data, regime):
        """
        渡されたデータを基に全項目を評価し、総合得点、時系列データ、分析コメントを返す。
        """
        # --- ▼▼▼ 修正箇所 ▼▼▼ ---
        # seriesが不正な場合、期待される3つの値を返し、エラーを防ぐ
        if series is None or series.empty or 'close' not in series.columns:
            return 0, series, "分析対象の市場データが不完全か、取得に失敗しました。"

        weights = self.WEIGHTS_TRENDING if regime == 'TRENDING' else self.WEIGHTS_RANGING
        
        tech_score, tech_comment = self._score_technical(series, weights['technical'])
        trend_score, trend_comment = self._score_trend(series, weights['trend'])
        sentiment_score, sentiment_comment = self._score_sentiment(fng_data, weights['sentiment'])
        
        ticker_symbol = f"{token_data.get('symbol', '').upper()}/USDT"
        order_book_score, order_book_comment = self._score_order_book(ticker_symbol, weights['order_book'])
        
        total_score = tech_score + trend_score + sentiment_score + order_book_score
        
        analysis_comments = (
            f"{tech_comment}\n\n{trend_comment}\n\n"
            f"{sentiment_comment}\n\n{order_book_comment}"
        )
        
        logging.info(f"Scoring for {token_data['symbol']}: TOTAL={total_score:.1f} (Regime: {regime})")
        
        # 正常終了時も、必ず3つの値を返す
        return total_score, series, analysis_comments
        # --- ▲▲▲ ここまで ▲▲▲ ---

    def _score_technical(self, series, max_score):
        try:
            if not all(k in series.columns for k in ['open', 'high', 'low', 'close']):
                raise ValueError("OHLC data missing.")
            
            # テクニカル指標を追加し、列名を小文字に統一
            series.ta.rsi(append=True)
            series.ta.macd(append=True)
            series.columns = [col.lower() for col in series.columns]

            rsi = series['rsi_14'].iloc[-1]
            macd_hist = series['macdh_12_26_9'].iloc[-1]
            
            score = 0
            if 30 < rsi < 65: score += max_score * 0.5
            if macd_hist > 0: score += max_score * 0.5
            
            comment = f"RSI({rsi:.1f})は中立圏、MACDヒストグラムは正の値。"
            return score, f"📈 テクニカル ({score:.1f}/{max_score}点)\n{comment}"
        except Exception as e:
            return 0, f"📈 テクニカル (0/{max_score}点)\n計算エラー: {e}"

    def _score_trend(self, series, max_score):
        try:
            if 'close' not in series.columns or len(series) < 200:
                 raise ValueError("Not enough data.")
            sma50 = series.ta.sma(50).iloc[-1]
            sma200 = series.ta.sma(200).iloc[-1]
            if sma50 > sma200:
                return max_score, f"📊 トレンド ({max_score}/{max_score}点)\n長期上昇トレンド。"
            return 0, f"📊 トレンド (0/{max_score}点)\n長期下降トレンド。"
        except Exception as e:
            return 0, f"📊 トレンド (0/{max_score}点)\n計算エラー: {e}"

    def _score_sentiment(self, fng_data, max_score):
        if not fng_data: return 0, f"🧠 センチメント (0/{max_score}点)\nデータなし。"
        score = (100 - fng_data['value']) / 100 * max_score
        return score, f"🧠 センチメント ({score:.1f}/{max_score}点)\n市場心理は「{fng_data['sentiment']}」。"

    def _score_order_book(self, ticker, max_score):
        if not self.exchange: return 0, f"📚 オーダーブック (0/{max_score}点)\n取引所未接続。"
        try:
            book = self.exchange.fetch_l2_order_book(ticker, limit=10)
            bids = sum(size for _, size in book['bids'])
            asks = sum(size for _, size in book['asks'])
            pressure = bids / (bids + asks) if (bids + asks) > 0 else 0.5
            score = pressure * max_score
            return score, f"📚 オーダーブック ({score:.1f}/{max_score}点)\n買い圧力が{(pressure*100):.1f}%。"
        except Exception:
            return 0, f"📚 オーダーブック (0/{max_score}点)\nデータ取得エラー。"
