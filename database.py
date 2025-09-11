# database.py (修正後のフルコード)
import os
import logging
import pickle
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, exc, LargeBinary
from config import (
    DB_FILE, 
    NOTIFICATION_COOLDOWN_HOURS, 
    ML_LABEL_LOOKBACK_HOURS,
    DATABASE_URL
)

# DATABASE_URLが設定されていればPostgreSQLを、なければSQLiteを使用
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine(f"sqlite:///{DB_FILE}")

def init_db():
    """データベースとテーブルを初期化する"""
    if not engine: return
    try:
        with engine.connect() as conn:
            with conn.begin():
                # (notification_history, market_data_historyのCREATE文は変更なし)
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification_history (
                    token_address VARCHAR(255) PRIMARY KEY, last_notified TIMESTAMP NOT NULL
                );"""))
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS market_data_history (
                    timestamp TIMESTAMP, token_address VARCHAR(255), price_usd FLOAT,
                    future_price_usd FLOAT, volume_h24 FLOAT, price_change_h1 FLOAT,
                    price_change_h24 FLOAT, social_mentions INTEGER, rsi_14 FLOAT,
                    PRIMARY KEY (timestamp, token_address)
                );"""))
                # ✅ 修正点: モデルを保存する新しいテーブルを追加
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS trained_models (
                    model_name VARCHAR(50) PRIMARY KEY,
                    model_data BYTEA,
                    trained_at TIMESTAMP
                );
                """))
        logging.info("PostgreSQL database tables checked/created successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize DB: {e}", exc_info=True)

# ✅ 修正点: モデルをDBに保存する関数
def save_model_to_db(model_name, model_object):
    """学習済みモデルをデータベースに保存する"""
    if not engine: return
    serialized_model = pickle.dumps(model_object)
    stmt = text("""
        INSERT INTO trained_models (model_name, model_data, trained_at) VALUES (:name, :data, :ts)
        ON CONFLICT (model_name) DO UPDATE SET model_data = EXCLUDED.model_data, trained_at = EXCLUDED.trained_at;
    """)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(stmt, {"name": model_name, "data": serialized_model, "ts": datetime.utcnow()})
    logging.info(f"Model '{model_name}' saved to database.")

# ✅ 修正点: モデルをDBから読み込む関数
def load_model_from_db(model_name):
    """データベースから学習済みモデルを読み込む"""
    if not engine: return None
    stmt = text("SELECT model_data FROM trained_models WHERE model_name = :name")
    with engine.connect() as conn:
        result = conn.execute(stmt, {"name": model_name}).fetchone()
        if result and result[0]:
            logging.info(f"Model '{model_name}' loaded from database.")
            return pickle.loads(result[0])
    logging.warning(f"Model '{model_name}' not found in database.")
    return None

# (他の関数 check_if_recently_notified, record_notificationなどは変更なし)
