import pandas as pd
import logging
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sqlalchemy import create_engine

# データベースとモデル操作の関数をインポート
from config import DATABASE_URL, DB_FILE
from database import save_model_to_db, load_model_from_db

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
        raise

    # ラベル付けされたデータ（答えがあるデータ）が十分にあるか確認
    if 'future_price_usd' not in df.columns or df['future_price_usd'].isnull().all():
        raise ValueError("Not enough labeled data to train. Please wait longer.")

    # ラベル付けされていない行を削除
    df.dropna(subset=['future_price_usd'], inplace=True)
    
    if len(df) < 100: # 学習に最低限必要なデータがあるか確認
        raise ValueError(f"Not enough labeled data. Found only {len(df)} records.")

    # 教師ラベル（AIが学習する「正解」）を定義
    df['future_price_grew'] = (df['future_price_usd'] >= df['price_usd'] * 1.10).astype(int)
    df['future_price_dumped'] = (df['future_price_usd'] <= df['price_usd'] * 0.90).astype(int)
    
    # 特徴量データがない行を削除
    df.dropna(inplace=True)
    if df.empty:
        logging.warning("DataFrame is empty after dropping NA. Cannot train.")
        return

    # モデルが学習する特徴量（AIへのヒント）を定義
    features = [
        'price_change_h1', 
        'price_change_h24', 
        'volume_h24', 
        'social_mentions', 
        'rsi_14', 
        'holder_change_24h' # Moralisから取得した新しい特徴量
    ]
    X = df[features]

    # --- 上昇予測モデル (Surge Model) の学習 ---
    y_surge = df['future_price_grew']
    if len(y_surge.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_surge, test_size=0.25, random_state=42, stratify=y_surge)
        surge_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        surge_model.fit(X_train, y_train)
        save_model_to_db('surge', surge_model) # 学習済みモデルをDBに保存
        logging.info(f"Surge Model Report:\n{classification_report(y_test, surge_model.predict(X_test))}")

    # --- 下落予測モデル (Dump Model) の学習 ---
    y_dump = df['future_price_dumped']
    if len(y_dump.unique()) > 1:
        X_train, X_test, y_train, y_test = train_test_split(X, y_dump, test_size=0.25, random_state=42, stratify=y_dump)
        dump_model = RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=-1)
        dump_model.fit(X_train, y_train)
        save_model_to_db('dump', dump_model) # 学習済みモデルをDBに保存
        logging.info(f"Dump Model Report:\n{classification_report(y_test, dump_model.predict(X_test))}")

def load_model(model_type='surge'):
    """データベースから学習済みモデルを読み込む"""
    return load_model_from_db(model_type)

def predict_probability(model, token_data):
    """与えられたモデルとトークンデータから、イベント発生確率を予測する"""
    if model is None: 
        return 0.5
        
    try:
        data = {
            'price_change_h1': token_data.get('priceChange', {}).get('h1', 0),
            'price_change_h24': token_data.get('priceChange', {}).get('h24', 0),
            'volume_h24': token_data.get('volume', {}).get('h24', 0),
            'social_mentions': token_data.get('social_data', {}).get('mentions', 0),
            'rsi_14': token_data.get('indicators', {}).get('rsi_14', 50),
            'holder_change_24h': token_data.get('onchain_data', {}).get('holder_change_24h', 0)
        }
        features_df = pd.DataFrame([data])
        # 予測確率 [クラス0の確率, クラス1の確率] のうち、クラス1の方を返す
        probability = model.predict_proba(features_df)[0][1]
        return probability
    except Exception as e:
        logging.error(f"Error during prediction: {e}")
        return 0.5
