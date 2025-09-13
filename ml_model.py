# ml_model.py
import pandas as pd
import yfinance as yf
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import pandas_ta as ta
import logging

def fetch_stock_data(ticker, period):
    """株価データを取得する"""
    logging.info(f"Fetching data for {ticker} over period {period}...")
    stock_data = yf.download(ticker, period=period)
    return stock_data

def preprocess_and_add_features(stock_data):
    """データの前処理とテクニカル指標（特徴量）の追加"""
    logging.info("Preprocessing data and adding technical indicators...")
    
    # テクニカル指標を追加
    stock_data.ta.rsi(append=True)
    stock_data.ta.macd(append=True)
    stock_data.ta.bbands(append=True)

    # ターゲット（目的変数）を作成
    stock_data['Returns'] = stock_data['Close'].pct_change()
    stock_data['Price_Dir'] = np.where(stock_data['Returns'] > 0, 1, 0) # 1 for up, 0 for down
    
    # NaN（非数）を含む行を削除
    stock_data = stock_data.dropna()
    
    # モデルが使用する特徴量を定義
    features = [
        'Open', 'High', 'Low', 'Close', 'Volume', 
        'RSI_14', 'MACDh_12_26_9', 'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0'
    ]
    
    X = stock_data[features]
    y = stock_data['Price_Dir']
    
    return X, y, stock_data

def train_model_and_get_prediction(X, y):
    """モデルを訓練し、翌日の予測値を取得する"""
    logging.info("Training model and making prediction...")
    
    # データを訓練用とテスト用に分割 (ここでは最新のデータで予測するため、分割は行わない)
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X, y) # 全データでモデルを訓練
    
    # 最後の行（最新のデータ）を使って翌日を予測
    last_row = X.iloc[[-1]]
    prediction = model.predict(last_row)
    
    return prediction[0]

def generate_signal(prediction, latest_data):
    """モデルの予測と最新のテクニカル指標から最終的な売買シグナルを生成"""
    logging.info("Generating final trading signal...")
    
    rsi_value = latest_data['RSI_14'].iloc[-1]
    
    if prediction == 1: # モデルが「上がる」と予測
        if rsi_value < 70: # RSIが過熱圏でなければ
            logging.info("Signal: BUY (Prediction is UP and RSI is not overbought)")
            return 'BUY'
        else:
            logging.warning("Signal: HOLD (Prediction is UP, but RSI is overbought)")
            return 'HOLD'
            
    else: # モデルが「下がる」と予測
        if rsi_value > 30: # RSIが売られすぎでなければ
            logging.info("Signal: SELL (Prediction is DOWN and RSI is not oversold)")
            return 'SELL'
        else:
            logging.warning("Signal: HOLD (Prediction is DOWN, but RSI is oversold)")
            return 'HOLD'

def start_model_analysis(ticker='^N225', period='1y'):
    """分析を実行し、最終的な売買シグナルを返すエントリーポイント関数"""
    try:
        stock_data = fetch_stock_data(ticker, period)
        if stock_data.empty:
            logging.error("Failed to fetch stock data.")
            return 'HOLD'
            
        X, y, processed_data = preprocess_and_add_features(stock_data)
        prediction = train_model_and_get_prediction(X, y)
        signal = generate_signal(prediction, processed_data)
        
        return signal
        
    except Exception as e:
        logging.error(f"An error occurred in model analysis: {e}")
        return 'HOLD' # エラー発生時は安全のためHOLDを返す
