import pandas as pd
import pandas_ta as ta
import logging

def calculate_technical_indicators(ohlcv_data_h1, ohlcv_data_d1):
    """
    1時間足と日足のデータからテクニカル指標を計算する
    """
    indicators = {}
    if not ohlcv_data_h1 or len(ohlcv_data_h1) < 20:
        return indicators

    try:
        # --- 1時間足の分析 ---
        df_h1 = pd.DataFrame(ohlcv_data_h1)
        df_h1['timestamp'] = pd.to_datetime(df_h1['timestamp'], unit='s')
        df_h1.set_index('timestamp', inplace=True)
        
        # RSI (期間14)
        df_h1.ta.rsi(length=14, append=True)
        indicators['rsi_14'] = df_h1['RSI_14'].iloc[-1]
        
        # ADX (期間14) - マーケット状況の判断用
        df_h1.ta.adx(length=14, append=True)
        indicators['adx_14'] = df_h1['ADX_14'].iloc[-1]
        
        # ピボットポイント (支持線・抵抗線)
        # (pandas-taには直接的なpivotがないため、手動で計算するか、他のライブラリを使用)
        # ここでは概念として、最新の終値を使うダミー実装
        last_close = df_h1['close'].iloc[-1]
        indicators['support_1'] = last_close * 0.98 # 2%下
        indicators['resistance_1'] = last_close * 1.02 # 2%上

        # --- 日足の分析 (長期トレンド) ---
        if ohlcv_data_d1 and len(ohlcv_data_d1) >= 20:
            df_d1 = pd.DataFrame(ohlcv_data_d1)
            # 20日移動平均線 (長期トレンドの方向性)
            df_d1['sma_20'] = ta.sma(df_d1['close'], length=20)
            last_price = df_d1['close'].iloc[-1]
            last_sma = df_d1['sma_20'].iloc[-1]
            if last_price > last_sma:
                indicators['long_term_trend'] = 'UP'
            elif last_price < last_sma:
                indicators['long_term_trend'] = 'DOWN'
            else:
                indicators['long_term_trend'] = 'SIDEWAYS'

        return {k: v for k, v in indicators.items() if pd.notna(v)}

    except Exception as e:
        logging.error(f"Failed to calculate technical indicators: {e}")
        return {}
