# ml_model.py
import pandas as pd
import logging
import pickle
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, LargeBinary, DateTime, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import pandas_ta as ta

# --- データベースのテーブル定義 ---
Base = declarative_base()
class AIModel(Base):
    __tablename__ = 'ai_models'
    id = Column(Integer, primary_key=True)
    model_data = Column(LargeBinary, nullable=False)
    accuracy = Column(Float, nullable=True)
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

# --- データ処理とモデル訓練 ---
def preprocess_and_add_features(df):
    try:
        df.ta.rsi(append=True)
        df.ta.macd(append=True)
        df.ta.bbands(append=True)
        df['Price_Dir'] = (df['Close'].pct_change() > 0).astype(int)
        df = df.dropna()
        features = ['Open', 'High', 'Low', 'Close', 'Volume', 'RSI_14', 'MACDh_12_26_9', 'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0']
        available_features = [f for f in features if f in df.columns]
        X = df[available_features]
        y = df['Price_Dir']
        return X, y, df
    except Exception as e:
        logging.error(f"Error during preprocessing: {e}")
        return pd.DataFrame(), pd.Series(), pd.DataFrame()

def train_and_evaluate_model(all_data):
    X, y, _ = preprocess_and_add_features(all_data)
    if X.empty: return None, 0
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    final_model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    final_model.fit(X, y)
    return final_model, accuracy

def run_daily_retraining(engine, data_aggregator):
    """1日1回実行されるメインの学習プロセス"""
    logging.info("🤖 Starting daily AI model retraining process...")
    all_data = data_aggregator.get_historical_data_for_training()
    if all_data.empty:
        logging.error("No data for retraining. Aborting."); return
    new_model, accuracy = train_and_evaluate_model(all_data)
    if new_model:
        save_model_to_db(new_model, engine, accuracy)
    logging.info("✅ Daily AI model retraining process finished.")

def check_performance_and_retrain_if_needed(engine, data_aggregator, state_manager):
    """現在のモデルのパフォーマンスを評価し, 閾値を下回っていたら再学習をトリガーする"""
    logging.info("🧠 Checking AI model performance...")
    trade_history = state_manager.trade_history
    if len(trade_history) < 10:
        logging.info("Not enough trade history to evaluate performance. Skipping."); return
    win_rate = state_manager.get_win_rate()
    logging.info(f"Current Win Rate: {win_rate:.2f}%")
    PERFORMANCE_THRESHOLD = 55.0
    if win_rate < PERFORMANCE_THRESHOLD:
        logging.warning(f"Performance ({win_rate:.2f}%) is below threshold ({PERFORMANCE_THRESHOLD}%). Triggering retraining.")
        run_daily_retraining(engine, data_aggregator)
    else:
        logging.info("Current model performance is satisfactory.")
