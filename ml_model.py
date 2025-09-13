# ml_model.py
import pandas as pd
import logging
import pickle
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, LargeBinary, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sklearn.ensemble import RandomForestClassifier

# ... (preprocess_and_add_features関数などは前回と同様)

# --- データベースモデル定義 ---
Base = declarative_base()
class AIModel(Base):
    __tablename__ = 'ai_models'
    id = Column(Integer, primary_key=True)
    model_data = Column(LargeBinary, nullable=False)
    accuracy = Column(Float, nullable=True) # モデルの精度を記録
    created_at = Column(DateTime, default=datetime.utcnow)

# --- データベース操作 ---
def save_model_to_db(model, engine, accuracy_score):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        serialized_model = pickle.dumps(model)
        new_model = AIModel(model_data=serialized_model, accuracy=accuracy_score)
        session.add(new_model)
        session.commit()
        logging.info(f"New AI model with accuracy {accuracy_score:.2f} saved to database.")
    except Exception as e:
        session.rollback(); logging.error(f"Failed to save model to DB: {e}")
    finally:
        session.close()

def load_latest_model_from_db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        latest_model_record = session.query(AIModel).order_by(AIModel.created_at.desc()).first()
        if latest_model_record:
            logging.info(f"Loading latest AI model (trained at {latest_model_record.created_at}) from database.")
            return pickle.loads(latest_model_record.model_data)
        return None
    except Exception as e:
        logging.error(f"Failed to load model from DB: {e}"); return None
    finally:
        session.close()

# --- モデルの訓練と分析 ---
def train_and_evaluate_model(all_data):
    """データからモデルを訓練し、評価する"""
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    # preprocess_and_add_featuresは前回提示したコードにあると仮定
    X, y, _ = preprocess_and_add_features(all_data)
    
    # データを訓練用とテスト用に分割して精度を評価
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    
    # 最終的なモデルは全データで再訓練する
    final_model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    final_model.fit(X, y) # 全データで学習
    
    return final_model, accuracy

def run_daily_retraining(engine, data_aggregator):
    """
    1日1回実行されるメインの学習プロセス。
    新しいデータを取得し、モデルを再訓練してDBに保存する。
    """
    logging.info("🤖 Starting daily AI model retraining process...")
    all_data = data_aggregator.get_all_chains_data()
    if all_data.empty:
        logging.error("No data available for retraining. Aborting.")
        return

    # モデルを訓練し、精度を評価
    new_model, accuracy = train_and_evaluate_model(all_data)
    
    # 新しいモデルをDBに保存
    save_model_to_db(new_model, engine, accuracy)
    logging.info("✅ Daily AI model retraining process finished.")
