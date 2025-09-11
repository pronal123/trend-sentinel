import pandas as pd
import joblib
import sqlite3
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from config import DB_FILE, MODEL_FILE

def train_model():
    """DBから履歴データを読み込み、モデルを学習・保存する"""
    logging.info("Starting model training...")
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT * FROM market_data_history", conn)

    # ✅ 下落ターゲットを追加: 1時間後に価格が10%以上下落したか
    df['future_price_grew'] = (df['future_price_usd'] > df['price_usd'] * 1.10).astype(int)
    df['future_price_dumped'] = (df['future_price_usd'] < df['price_usd'] * 0.90).astype(int)
    df.dropna(inplace=True)

    if len(df) < 200:
        logging.warning(f"Not enough data to train model. Found only {len(df)} records.")
        return

    features = ['price_change_h1', 'price_change_h24', 'volume_h24', 'social_mentions']
    
    # --- 上昇予測モデルの学習 ---
    target_surge = 'future_price_grew'
    X = df[features]
    y_surge = df[target_surge]

    if len(y_surge.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_surge, test_size=0.25, random_state=42, stratify=y_surge)
        surge_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        surge_model.fit(X_train, y_train)
        joblib.dump(surge_model, MODEL_FILE + "_surge.joblib")
        logging.info(f"Surge model trained and saved.")

    # --- 下落予測モデルの学習 ---
    target_dump = 'future_price_dumped'
    y_dump = df[target_dump]

    if len(y_dump.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_dump, test_size=0.25, random_state=42, stratify=y_dump)
        dump_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        dump_model.fit(X_train, y_train)
        joblib.dump(dump_model, MODEL_FILE + "_dump.joblib")
        logging.info(f"Dump model trained and saved.")

def load_model(model_type='surge'):
    """指定されたタイプの学習済みモデルを読み込む"""
    try:
        return joblib.load(MODEL_FILE + f"_{model_type}.joblib")
    except FileNotFoundError:
        return None

def predict_probability(model, token_data):
    """単一トークンのデータから確率を予測する共通関数"""
    if model is None: return 0.5
    try:
        data = {
            'price_change_h1': token_data.get('priceChange', {}).get('h1', 0),
            'price_change_h24': token_data.get('priceChange', {}).get('h24', 0),
            'volume_h24': token_data.get('volume', {}).get('h24', 0),
            'social_mentions': token_data.get('social_data', {}).get('mentions', 0)
        }
        features_df = pd.DataFrame([data])
        # クラス1 (上昇または下落) の確率を返す
        probability = model.predict_proba(features_df)[0][1]
        return probability
    except Exception as e:
        logging.error(f"Error during prediction: {e}")
        return 0.5
