# features.py
import pandas as pd
import pandas_ta as ta
import logging

def calculate_technical_indicators(ohlcv_data):
    """
    過去の価格データフレームからテクニカル指標（RSIなど）を計算する。

    Args:
        ohlcv_data (list of dict): APIから取得したOHLCVデータのリスト。
        例: [{'timestamp': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}, ...]

    Returns:
        dict: 計算された最新のテクニカル指標を含む辞書。
    """
    if not ohlcv_data or len(ohlcv_data) < 14:
        # RSI計算に必要な最低限のデータがない場合は空の辞書を返す
        return {}

    try:
        # リストからPandas DataFrameを作成
        df = pd.DataFrame(ohlcv_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # pandas-taを使ってRSIを計算 (期間14)
        df.ta.rsi(length=14, append=True)
        
        # 計算された最新の指標を取得
        latest_indicators = {
            'rsi_14': df['RSI_14'].iloc[-1] if 'RSI_14' in df.columns and not pd.isna(df['RSI_14'].iloc[-1]) else None
        }
        return latest_indicators

    except Exception as e:
        logging.error(f"Failed to calculate technical indicators: {e}")
        return {}