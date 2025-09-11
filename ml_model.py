import pandas as pd
import joblib
import sqlite3
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from config import DB_FILE, MODEL_FILE, DATABASE_URL
from sqlalchemy import create_engine

# DATABASE_URLが設定されていればPostgreSQLを、なければSQLiteを使用
if DATABASE_URL:
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(f"sqlite:///{DB_FILE}")

def train_model():
    """DBから履歴データを読み込み、上昇モデルと下落モデルの両方を学習・保存する"""
    logging.info("Starting model training...")
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query("SELECT * FROM market_data_history", conn)
    except Exception as e:
        logging.error(f"Failed to read data from database: {e}")
        return

    # ✅ 修正点：'future_price_usd'列の存在とデータの中身を確認する
    if 'future_price_usd' not in df.columns or df['future_price_usd'].isnull().all():
        error_msg = "Not enough labeled data to train. Please wait for at least 1-2 hours for data to be processed."
        logging.error(error_msg)
        # このエラーメッセージを返すことで、/trainエンドポイントの呼び出し元に状況を伝える
        raise ValueError(error_msg)

    # 「答え合わせ」が完了していない行を削除
    df.dropna(subset=['future_price_usd'], inplace=True)
    
    if len(df) < 100: # 学習に十分なデータがあるか確認
        error_msg = f"Not enough labeled data to train. Found only {len(df)} records. Please wait longer."
        logging.error(error_msg)
        raise ValueError(error_msg)

    # 教師ラベルを定義
    df['future_price_grew'] = (df['future_price_usd'] >= df['price_usd'] * 1.10).astype(int)
    df['future_price_dumped'] = (df['future_price_usd'] <= df['price_usd'] * 0.90).astype(int)
    
    # 特徴量エンジニアリングで生成した特徴量などをクレンジング
    df.dropna(inplace=True)
    if df.empty:
        logging.warning("DataFrame is empty after dropping NA. Cannot train.")
        return

    features = ['price_change_h1', 'price_change_h24', 'volume_h24', 'social_mentions', 'rsi_14']
    X = df[features]

    # --- 上昇予測モデル (Surge Model) の学習 ---
    y_surge = df['future_price_grew']
    if len(y_surge.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_surge, test_size=0.25, random_state=42, stratify=y_surge)
        surge_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        surge_model.fit(X_train, y_train)
        joblib.dump(surge_model, f"{MODEL_FILE}_surge.joblib")
        logging.info(f"Surge model trained and saved. Report:\n{classification_report(y_test, surge_model.predict(X_test))}")

    # --- 下落予測モデル (Dump Model) の学習 ---
    y_dump = df['future_price_dumped']
    if len(y_dump.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_dump, test_size=0.25, random_state=42, stratify=y_dump)
        dump_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        dump_model.fit(X_train, y_train)
        joblib.dump(dump_model, f"{MODEL_FILE}_dump.joblib")
        logging.info(f"Dump model trained and saved. Report:\n{classification_report(y_test, dump_model.predict(X_test))}")

# ... (load_model, predict_probability関数は変更なし) ...
def load_model(model_type='surge'):
    try:
        model_path = f"{MODEL_FILE}_{model_type}.joblib"
        return joblib.load(model_path)
    except FileNotFoundError:
        logging.warning(f"Model file not found: {model_path}")
        return None

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
        probability = model.predict_proba(features_df)[0][1]
        return probability
    except Exception as e:
        logging.error(f"Error during prediction: {e}")
        return 0.5
