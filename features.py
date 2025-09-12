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
        # --- 1時間足の分析 (短期的な勢い) ---
        df_h1 = pd.DataFrame(ohlcv_data_h1)
        df_h1['timestamp'] = pd.to_datetime(df_h1['timestamp'], unit='s')
        df_h1.set_index('timestamp', inplace=True)
        
        df_h1.ta.rsi(length=14, append=True)
        indicators['rsi_14'] = df_h1['RSI_14'].iloc[-1]
        
        df_h1.ta.adx(length=14, append=True)
        indicators['adx_14'] = df_h1['ADX_14'].iloc[-1]
        
        last_close = df_h1['close'].iloc[-1]
        indicators['support_1'] = last_close * 0.98
        indicators['resistance_1'] = last_close * 1.02

        # --- 日足の分析 (長期的なトレンド方向) ---
        if ohlcv_data_d1 and len(ohlcv_data_d1) >= 20:
            df_d1 = pd.DataFrame(ohlcv_data_d1)
            df_d1['timestamp'] = pd.to_datetime(df_d1['timestamp'], unit='s')
            # 20日単純移動平均線 (SMA) を計算
            sma_20 = ta.sma(df_d1['close'], length=20)
            if sma_20 is not None and not sma_20.empty:
                last_price_d1 = df_d1['close'].iloc[-1]
                last_sma_d1 = sma_20.iloc[-1]
                if pd.notna(last_price_d1) and pd.notna(last_sma_d1):
                    if last_price_d1 > last_sma_d1:
                        indicators['long_term_trend'] = 'UP'
                    elif last_price_d1 < last_sma_d1:
                        indicators['long_term_trend'] = 'DOWN'
                    else:
                        indicators['long_term_trend'] = 'SIDEWAYS'

        # 計算できた指標のみを返す (NaNなどを除く)
        return {k: v for k, v in indicators.items() if pd.notna(v)}

    except Exception as e:
        logging.error(f"Failed to calculate technical indicators: {e}", exc_info=True)
        return {}
