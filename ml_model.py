# ml_model.py
import pandas as pd
import logging
import pickle
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, LargeBinary, DateTime, Float # <--- Floatをインポート
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import pandas_ta as ta

# --- データベースのテーブル定義 ---
Base = declarative_base()

class AIModel(Base):
    """
    訓練済みAIモデルをデータベースに保存するためのテーブル定義。
    """
    __tablename__ = 'ai_models'
    id = Column(Integer, primary_key=True)
    model_data = Column(LargeBinary, nullable=False)
    accuracy = Column(Float, nullable=True) # モデルの精度を記録
    created_at = Column(DateTime, default=datetime.utcnow)

# --- データベース操作 ---
def save_model_to_db(model, engine, accuracy_score):
    """訓練済みのモデルを指定されたデータベースに保存する。"""
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        serialized_model = pickle.dumps(model)
        new_model = AIModel(model_data=serialized_model, accuracy=accuracy_score)
        session.add(new_model)
        session.commit()
        logging.info(f"New AI model with accuracy {accuracy_score:.2f} has been saved to the database.")
    except Exception as e:
        session.rollback()
        logging.error(f"Failed to save model to DB: {e}")
    finally:
        session.close()

def load_latest_model_from_db(engine):
    """データベースから最新の訓練済みモデルをロードする。"""
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        latest_model_record = session.query(AIModel).order_by(AIModel.created_at.desc()).first()
        if latest_model_record:
            logging.info(f"Loading latest AI model (trained at {latest_model_record.created_at}, accuracy: {latest_model_record.accuracy:.2f}) from database.")
            return pickle.loads(latest_model_record.model_data)
        logging.warning("No model found in the database.")
        return None
    except Exception as e:
        logging.error(f"Failed to load model from DB: {e}")
        return None
    finally:
        session.close()

# --- データ処理とモデル訓練 ---
def preprocess_and_add_features(df):
    """データの前処理とテクニカル指標（特徴量）を追加する。"""
    try:
        # テクニカル指標を追加
        df.ta.rsi(append=True)
        df.ta.macd(append=True)
        df.ta.bbands(append=True)

        # ターゲット（目的変数）を作成
        df['Price_Dir'] = (df['Close'].pct_change() > 0).astype(int)
        df = df.dropna()
        
        # モデルが使用する特徴量を定義
        features = [
            'Open', 'High', 'Low', 'Close', 'Volume', 
            'RSI_14', 'MACDh_12_26_9', 'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0'
        ]
        
        # 特徴量が存在するか確認
        available_features = [f for f in features if f in df.columns]
        if len(available_features) < len(features):
            logging.warning(f"Some features are missing. Available: {available_features}")

        X = df[available_features]
        y = df['Price_Dir']
        
        return X, y, df
    except Exception as e:
        logging.error(f"Error during preprocessing: {e}")
        return pd.DataFrame(), pd.Series(), pd.DataFrame()


def train_and_evaluate_model(all_data):
    """データからモデルを訓練し、精度を評価して最終モデルを返す。"""
    X, y, _ = preprocess_and_add_features(all_data)
    if X.empty:
        return None, 0

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    # 最終的なモデルは全データで再訓練する
    final_model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    final_model.fit(X, y)
    
    return final_model, accuracy

def run_daily_retraining(engine, data_aggregator):
    """
    1日1回実行されるメインの学習プロセス。
    新しいデータを取得し、モデルを再訓練してDBに保存する。
    """
    logging.info("🤖 Starting daily AI model retraining process...")
    # data_aggregatorはyfinanceなどからデータを取得する前提
    all_data = data_aggregator.get_historical_data_for_training()
    if all_data.empty:
        logging.error("No data available for retraining. Aborting.")
        return

    new_model, accuracy = train_and_evaluate_model(all_data)
    
    if new_model:
        save_model_to_db(new_model, engine, accuracy)
    
    logging.info("✅ Daily AI model retraining process finished.")
