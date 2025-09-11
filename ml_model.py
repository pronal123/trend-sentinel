# ml_model.py (修正後のフルコード)
import pandas as pd
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from config import DATABASE_URL, DB_FILE
from sqlalchemy import create_engine
# ✅ 修正点: データベース操作関数をインポート
from database import save_model_to_db, load_model_from_db

if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(f"sqlite:///{DB_FILE}")

def train_model():
    logging.info("Starting model training...")
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query("SELECT * FROM market_data_history", conn)
    except Exception as e:
        logging.error(f"Failed to read data from database: {e}")
        raise

    if 'future_price_usd' not in df.columns or df['future_price_usd'].isnull().all():
        raise ValueError("Not enough labeled data to train. Please wait longer.")

    df.dropna(subset=['future_price_usd'], inplace=True)
    if len(df) < 100:
        raise ValueError(f"Not enough labeled data. Found only {len(df)} records.")

    df['future_price_grew'] = (df['future_price_usd'] >= df['price_usd'] * 1.10).astype(int)
    df['future_price_dumped'] = (df['future_price_usd'] <= df['price_usd'] * 0.90).astype(int)
    df.dropna(inplace=True)

    features = ['price_change_h1', 'price_change_h24', 'volume_h24', 'social_mentions', 'rsi_14']
    X = df[features]

    # --- 上昇予測モデルの学習 ---
    y_surge = df['future_price_grew']
    if len(y_surge.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_surge, test_size=0.25, random_state=42, stratify=y_surge)
        surge_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        surge_model.fit(X_train, y_train)
        # ✅ 修正点: DBにモデルを保存
        save_model_to_db('surge', surge_model)

    # --- 下落予測モデルの学習 ---
    y_dump = df['future_price_dumped']
    if len(y_dump.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_dump, test_size=0.25, random_state=42, stratify=y_dump)
        dump_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        dump_model.fit(X_train, y_train)
        # ✅ 修正点: DBにモデルを保存
        save_model_to_db('dump', dump_model)

def load_model(model_type='surge'):
    # ✅ 修正点: DBからモデルを読み込む
    return load_model_from_db(model_type)

def predict_probability(model, token_data):
    if model is None: return 0.5
    try:
        data = {
            'price_change_h1': token_data.get('priceChange', {}).get('h1', 0),
            'price_change_h24': token_data.get('priceChange', {}).get('h24', 0),
            'volume_h24': token_data.get('volume', {}).get('h24', 0),
            'social_mentions': token_data.get('social_data', {}).get('mentions', 0),
            'rsi_14': token_data.get('indicators', {}).get('rsi_14', 50)
        }
        features_df = pd.DataFrame([data])
        return model.predict_proba(features_df)[0][1]
    except Exception as e:
        logging.error(f"Error during prediction: {e}")
        return 0.5
