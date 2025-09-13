# ml_model.py
# ... (他のインポート)
import pickle
from sqlalchemy import create_engine, Column, Integer, LargeBinary, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

# --- データベースモデル定義 ---
Base = declarative_base()
class AIModel(Base):
    __tablename__ = 'ai_models'
    id = Column(Integer, primary_key=True)
    model_data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- データベース操作関数 ---
def save_model_to_db(model, engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        serialized_model = pickle.dumps(model)
        new_model = AIModel(model_data=serialized_model)
        session.add(new_model)
        session.commit()
        logging.info("New AI model has been saved to the database.")
    except Exception as e:
        session.rollback()
        logging.error(f"Failed to save model to DB: {e}")
    finally:
        session.close()

def load_model_from_db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        latest_model_record = session.query(AIModel).order_by(AIModel.created_at.desc()).first()
        if latest_model_record:
            logging.info("Loading latest AI model from database.")
            return pickle.loads(latest_model_record.model_data)
        logging.warning("No model found in database. A new one will be trained.")
        return None
    except Exception as e:
        logging.error(f"Failed to load model from DB: {e}")
        return None
    finally:
        session.close()

# --- モデル訓練・分析関数 ---
def train_and_save_new_model(engine, data_aggregator):
    """新しいデータを取得し、モデルを再訓練してDBに保存する"""
    logging.info("Starting new model training process...")
    all_data = data_aggregator.get_all_chains_data()
    if all_data.empty:
        logging.error("No data for training. Aborting.")
        return
    
    X, y, _ = preprocess_and_add_features(all_data)
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X, y)
    save_model_to_db(model, engine)
    return model

def start_model_analysis(engine, ticker='^N225', period='1y'):
    """DBからモデルをロードして分析を実行。モデルがなければ訓練する"""
    model = load_model_from_db(engine)
    if not model:
        # DBにモデルがない場合、初回訓練を行う（実際はtrain_and_save_new_modelを呼び出すべき）
        # この例では簡略化のため、その場で簡易訓練
        # ...
        pass
    
    # ... (モデルを使った分析ロジック)
    # signal = generate_signal(prediction, latest_data)
    # return signal
