# market_regime_detector.py
import pandas_ta as ta
import logging

class MarketRegimeDetector:
    def get_market_regime(self, series):
        """
        ADX指標を用いて現在の市場レジームを判断する。
        戻り値: 'TRENDING' or 'RANGING'
        """
        try:
            # ADXを計算 (14期間)
            adx = series.ta.adx()
            adx_value = adx['ADX_14'].iloc[-1]
            
            logging.info(f"Current ADX value: {adx_value:.2f}")

            if adx_value > 25:
                logging.info("Market Regime: TRENDING")
                return 'TRENDING'
            else:
                logging.info("Market Regime: RANGING")
                return 'RANGING'
        except Exception as e:
            logging.error(f"Could not determine market regime: {e}")
            return 'RANGING' # 不明な場合は安全なレンジ判断
