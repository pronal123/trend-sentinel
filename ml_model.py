# ml_model.py
import pandas as pd
import yfinance as yf
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg') # GUIバックエンドなしで動作させるために必要

def fetch_stock_data(ticker, period):
    stock_data = yf.download(ticker, period=period)
    return stock_data

def preprocess_data(stock_data):
    stock_data['Returns'] = stock_data['Close'].pct_change()
    stock_data['Price_Dir'] = np.where(stock_data['Returns'] > 0, 1, 0) # 1 for up, 0 for down
    stock_data = stock_data.dropna()
    features = ['Open', 'High', 'Low', 'Close', 'Volume']
    X = stock_data[features]
    y = stock_data['Price_Dir']
    return X, y, stock_data

def train_model_and_predict(X, y):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    print(f"Model Accuracy: {accuracy:.2f}")
    
    # Predict tomorrow
    last_row = X.iloc[[-1]]
    tomorrow_prediction = model.predict(last_row)
    return tomorrow_prediction[0]

def run_prediction(ticker, period):
    stock_data = fetch_stock_data(ticker, period)
    X, y, processed_data = preprocess_data(stock_data)
    prediction = train_model_and_predict(X, y)

    prediction_text = "UP" if prediction == 1 else "DOWN"
    print(f"Predicted direction for tomorrow: {prediction_text}")

    # Plot the chart
    plot_data = processed_data.tail(60)
    title = f"{ticker} Stock Price - Prediction for Tomorrow: {prediction_text}"
    mpf.plot(plot_data, type='candle', style='yahoo',
             title=title,
             ylabel='Price (JPY)',
             volume=True,
             savefig='stock_chart.png') # Save the plot to a file
    print("Chart saved to stock_chart.png")

def start_model_prediction():
    """予測モデルの実行を開始するためのエントリーポイント関数"""
    print("🚀 Starting stock trend prediction model...")
    run_prediction('^N225', '1y')
    print("✅ Prediction model run completed.")

if __name__ == "__main__":
    start_model_prediction()
