import pandas as pd
import joblib
import sqlite3
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from config import DB_FILE, MODEL_FILE

def train_model():
    """DBから履歴データを読み込み、上昇モデルと下落モデルの両方を学習・保存する"""
    logging.info("Starting model training...")
    with sqlite3.connect(DB_FILE) as conn:
        # データベースから全データを読み込む
        df = pd.read_sql_query("SELECT * FROM market_data_history", conn)

    # ラベル付けされていないデータを削除
    df.dropna(subset=['future_price_usd'], inplace=True)
    if len(df) < 200:
        logging.warning(f"Not enough data to train model. Found only {len(df)} labeled records.")
        return

    # 教師ラベルを定義
    # 価格が1時間後に10%以上「上昇」したか
    df['future_price_grew'] = (df['future_price_usd'] >= df['price_usd'] * 1.10).astype(int)
    # 価格が1時間後に10%以上「下落」したか
    df['future_price_dumped'] = (df['future_price_usd'] <= df['price_usd'] * 0.90).astype(int)
    
    # 特徴量エンジニアリングで生成した特徴量などをクレンジング
    df.dropna(inplace=True)
    if df.empty:
        logging.warning("DataFrame is empty after dropping NA values. Cannot train model.")
        return

    # モデルが学習する特徴量を定義 (RSIを追加)
    features = ['price_change_h1', 'price_change_h24', 'volume_h24', 'social_mentions', 'rsi_14']
    X = df[features]

    # --- 上昇予測モデル (Surge Model) の学習 ---
    target_surge = 'future_price_grew'
    y_surge = df[target_surge]
    if len(y_surge.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_surge, test_size=0.25, random_state=42, stratify=y_surge)
        surge_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        surge_model.fit(X_train, y_train)
        joblib.dump(surge_model, MODEL_FILE + "_surge.joblib")
        logging.info("Surge model trained and saved.")
        logging.info(f"Surge Model Report:\n{classification_report(y_test, surge_model.predict(X_test))}")

    # --- 下落予測モデル (Dump Model) の学習 ---
    target_dump = 'future_price_dumped'
    y_dump = df[target_dump]
    if len(y_dump.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_dump, test_size=0.25, random_state=42, stratify=y_dump)
        dump_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        dump_model.fit(X_train, y_train)
        joblib.dump(dump_model, MODEL_FILE + "_dump.joblib")
        logging.info("Dump model trained and saved.")
        logging.info(f"Dump Model Report:\n{classification_report(y_test, dump_model.predict(X_test))}")

def load_model(model_type='surge'):
    """指定されたタイプの学習済みモデルを読み込む ('surge' または 'dump')"""
    try:
        model_path = MODEL_FILE + f"_{model_type}.joblib"
        return joblib.load(model_path)
    except FileNotFoundError:
        logging.warning(f"Model file not found: {model_path}")
        return None

def predict_probability(model, token_data):
    """
    与えられたモデルと単一トークンのデータから、
    イベント（上昇または下落）が発生する確率を予測する。
    """
    if model is None:
        return 0.5  # モデルが存在しない場合は中立の確率50%を返す
    
    try:
        # モデルが学習した特徴量をtoken_dataから抽出
        data = {
            'price_change_h1': token_data.get('priceChange', {}).get('h1', 0),
            'price_change_h24': token_data.get('priceChange', {}).get('h24', 0),
            'volume_h24': token_data.get('volume', {}).get('h24', 0),
            'social_mentions': token_data.get('social_data', {}).get('mentions', 0),
            'rsi_14': token_data.get('indicators', {}).get('rsi_14', 50)  # RSIを追加。データがない場合は中立値の50を使用
        }
        
        # Pandas DataFrameに変換
        features_df = pd.DataFrame([data])
        
        # クラス1 (上昇または下落) に分類される確率を予測して返す
        probability = model.predict_proba(features_df)[0][1]
        return probability
        
    except Exception as e:
        logging.error(f"Error during prediction: {e}")
        return 0.5 # エラーが発生した場合も中立の確率を返す
