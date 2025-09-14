# scoring_engine.py
import logging
import pandas as pd
import pandas_ta as ta

class ScoringEngine:
    """
    市場の多角的分析とスコアリングを担当する。
    市場レジームを自動判定し、分析ウェイトを動的に変更して総合スコアを算出する。
    """

    def __init__(self, exchange):
        self.exchange = exchange
        # レジーム別のウェイトを定義
        # トレンド相場では、トレンドと短期モメンタムを重視
        self.WEIGHTS_TRENDING = {
            'momentum': 35, 'trend': 40, 'sentiment': 10, 'order_book': 15
        }
        # レンジ相場では、逆張り指標とオーダーブックを重視
        self.WEIGHTS_RANGING = {
            'momentum': 15, 'trend': 5, 'sentiment': 40, 'order_book': 40
        }

    def _determine_market_regime(self, series):
        """
        チャートデータから市場レジーム（トレンド相場かレンジ相場か）を判定する。
        ここではADX指標を使用。ADXが25以上ならトレンド相場と判断。
        """
        try:
            if series is None or len(series) < 25:
                return 'RANGING', "データ不足のためレンジ相場と判断"
            
            # ADXを計算
            adx_df = series.ta.adx()
            adx_value = adx_df['ADX_14'].iloc[-1]
            
            if adx_value > 25:
                return 'TRENDING', f"ADX({adx_value:.1f})が25を超えており、トレンド相場と判断"
            else:
                return 'RANGING', f"ADX({adx_value:.1f})が25以下であり、レンジ相場と判断"
        except Exception as e:
            logging.error(f"Failed to determine market regime: {e}")
            return 'RANGING', f"レジーム判定エラー: {e}"

    def generate_score_and_analysis(self, token_data, series, fng_data, signal_type):
        """
        全ての分析を実行し、総合スコア、分析コメント、レジームを返す。
        """
        if series is None or series.empty or 'close' not in series.columns:
            return 0, "分析対象の市場データが不完全か、取得に失敗しました。", 'UNKNOWN'

        # 1. 市場レジームを判定
        regime, regime_comment = self._determine_market_regime(series)
        weights = self.WEIGHTS_TRENDING if regime == 'TRENDING' else self.WEIGHTS_RANGING

        # 2. 各項目をスコアリング
        momentum_score, momentum_comment = self._score_momentum(token_data, series, weights['momentum'])
        trend_score, trend_comment = self._score_trend(series, weights['trend'])
        sentiment_score, sentiment_comment = self._score_sentiment(fng_data, weights['sentiment'], signal_type)
        
        # 取引所のティッカー形式に変換
        ticker_symbol = token_data.get('symbol', '').upper() + "/USDT"
        order_book_score, order_book_comment = self._score_order_book(ticker_symbol, weights['order_book'])

        # 3. 総合スコアを計算
        total_score = momentum_score + trend_score + sentiment_score + order_book_score
        
        # 4. 最終的な分析コメントを生成
        full_analysis = (
            f"🔹 *総合スコア: {total_score:.1f} / 100 点*\n"
            f"🔹 *市場レジーム: {regime}* ({regime_comment})\n\n"
            f"{momentum_comment}\n\n"
            f"{trend_comment}\n\n"
            f"{sentiment_comment}\n\n"
            f"{order_book_comment}"
        )
        
        logging.info(f"Scoring for {token_data['symbol']}: TOTAL={total_score:.1f} (Regime: {regime})")
        
        return total_score, full_analysis, regime

    def _score_momentum(self, token_data, series, max_score):
        """短期的な勢い（モメンタム）を評価する"""
        try:
            series.ta.rsi(append=True)
            series.ta.macd(append=True)
            series.columns = [col.lower() for col in series.columns]

            price_change_1h = token_data.get('price_change_1h', 0)
            rsi = series['rsi_14'].iloc[-1]
            macd_hist = series['macdh_12_26_9'].iloc[-1]
            
            score = 0
            # 1h価格変化が強いほど高スコア
            score += min(abs(price_change_1h) / 10, 1) * max_score * 0.6
            # MACDヒストグラムがシグナル方向に合致していれば加点
            if (price_change_1h > 0 and macd_hist > 0) or (price_change_1h < 0 and macd_hist < 0):
                score += max_score * 0.4
            
            comment = f"1h価格変化は{price_change_1h:.2f}%。RSIは{rsi:.1f}、MACDヒストグラムは{macd_hist:.4f}。"
            return score, f"📈 *モメンタム ({score:.1f}/{max_score}点)*\n{comment}"
        except Exception as e:
            return 0, f"📈 *モメンタム (0/{max_score}点)*\n計算エラー: {e}"

    def _score_trend(self, series, max_score):
        """長期的なトレンドの方向性を評価する"""
        try:
            if len(series) < 200: return 0, f"📊 *トレンド (0/{max_score}点)*\n長期データ不足。"
            sma50 = series.ta.sma(50).iloc[-1]
            sma200 = series.ta.sma(200).iloc[-1]
            if sma50 > sma200:
                return max_score, f"📊 *トレンド ({max_score:.1f}/{max_score}点)*\nゴールデンクロス（50日線 > 200日線）形成中。長期上昇トレンド。"
            else:
                return 0, f"📊 *トレンド (0/{max_score}点)*\nデッドクロス（50日線 < 200日線）形成中。長期下降トレンド。"
        except Exception as e:
            return 0, f"📊 *トレンド (0/{max_score}点)*\n計算エラー: {e}"

    def _score_sentiment(self, fng_data, max_score, signal_type):
        """市場心理（Fear & Greed）を評価する"""
        if not fng_data or 'value' not in fng_data:
             return 0, f"🧠 *センチメント (0/{max_score}点)*\nデータなし。"
        
        fng_value = fng_data['value']
        sentiment = fng_data['sentiment']
        score = 0
        
        # LONGシグナルの場合、市場が恐怖に傾いているほど高スコア（逆張り）
        if signal_type == 'LONG' and fng_value < 40:
            score = (50 - fng_value) / 50 * max_score
        # SHORTシグナルの場合、市場が強欲に傾いているほど高スコア（逆張り）
        elif signal_type == 'SHORT' and fng_value > 60:
            score = (fng_value - 50) / 50 * max_score
            
        comment = f"市場心理は「{sentiment}」(F&G指数: {fng_value})。"
        return score, f"🧠 *センチメント ({score:.1f}/{max_score}点)*\n{comment}"

    def _score_order_book(self, ticker, max_score):
        """オーダーブックから直近の買い圧力・売り圧力を評価する"""
        if not self.exchange: return 0, f"📚 *オーダーブック (0/{max_score}点)*\n取引所未接続。"
        try:
            book = self.exchange.fetch_l2_order_book(ticker, limit=100)
            bids = sum(size for _, size in book['bids'])
            asks = sum(size for _, size in book['asks'])
            pressure = bids / (bids + asks) if (bids + asks) > 0 else 0.5
            score = pressure * max_score
            comment = f"直近のオーダーブックにおける買い圧力は{(pressure*100):.1f}%です。"
            return score, f"📚 *オーダーブック ({score:.1f}/{max_score}点)*\n{comment}"
        except Exception:
            return 0, f"📚 *オーダーブック (0/{max_score}点)*\nデータ取得エラー。"
