import pandas as pd
import joblib
import sqlite3
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

# config.pyからインポートすることを想定
# from config import DB_FILE, MODEL_FILE
# 以下はハードコードした仮の値
DB_FILE = "sentinel_data.db"
MODEL_FILE = "trend_classifier.joblib"


def train_model():
    """DBから履歴データを読み込み、モデルを学習・保存する（手動実行用）"""
    logging.info("Starting model training...")
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT * FROM market_data_history WHERE future_price_grew IS NOT NULL", conn)

    if len(df) < 200:
        logging.warning(f"Not enough data to train model. Found only {len(df)} labeled records.")
        return

    df.dropna(inplace=True)
    if df.empty:
        logging.warning("DataFrame is empty after dropping NA values. Cannot train model.")
        return

    features = ['price_change_h1', 'price_change_h24', 'volume_h24', 'social_mentions']
    target = 'future_price_grew'
    X = df[features]
    y = df[target]

    if len(y.unique()) < 2:
        logging.warning("The target variable has only one class. Cannot train model.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
    model.fit(X_train, y_train)

    logging.info("Model training complete. Evaluating performance...")
    predictions = model.predict(X_test)
    report = classification_report(y_test, predictions)
    logging.info(f"Classification Report:\n{report}")

    joblib.dump(model, MODEL_FILE)
    logging.info(f"Model trained and saved to {MODEL_FILE}")

def load_model():
    """学習済みモデルを読み込む"""
    try:
        return joblib.load(MODEL_FILE)
    except FileNotFoundError:
        # ログに警告を出すが、プログラムは続行させる
        logging.warning(f"ML model file '{MODEL_FILE}' not found. Predictions will be neutral.")
        return None

def predict_surge_probability(model, token_data):
    """単一トークンのデータから急騰確率を予測する"""
    # モデルが存在しない場合は、中立的な確率0.5を返す
    if model is None: 
        return 0.5
        
    try:
        data = {
            'price_change_h1': token_data.get('priceChange', {}).get('h1', 0),
            'price_change_h24': token_data.get('priceChange', {}).get('h24', 0),
            'volume_h24': token_data.get('volume', {}).get('h24', 0),
            'social_mentions': token_data.get('social_data', {}).get('mentions', 0)
        }
        features_df = pd.DataFrame([data])
        # モデルが期待する特徴量の順序に合わせる
        features_df = features_df[['price_change_h1', 'price_change_h24', 'volume_h24', 'social_mentions']]
        
        # クラス1（急騰）の確率を返す
        probability = model.predict_proba(features_df)[0][1]
        return probability
    except Exception as e:
        logging.error(f"Error during prediction: {e}")
        return 0.5 # エラー時も中立的な値を返す

