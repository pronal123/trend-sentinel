import os
import logging
import pickle
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from config import (
    DB_FILE,
    NOTIFICATION_COOLDOWN_HOURS,
    ML_LABEL_LOOKBACK_HOURS,
    DATABASE_URL
)

# DATABASE_URLが設定されていればPostgreSQLを、なければSQLiteをフォールバックとして使用
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine(f"sqlite:///{DB_FILE}")

def init_db():
    """データベースとテーブルを初期化する"""
    if not engine:
        logging.error("Database engine not created. Check DATABASE_URL.")
        return
    try:
        with engine.connect() as conn:
            with conn.begin(): # トランザクション内で実行
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification_history (
                    token_address VARCHAR(255) PRIMARY KEY,
                    last_notified TIMESTAMP NOT NULL
                );
                """))
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS market_data_history (
                    timestamp TIMESTAMP,
                    token_address VARCHAR(255),
                    price_usd FLOAT,
                    future_price_usd FLOAT,
                    volume_h24 FLOAT,
                    price_change_h1 FLOAT,
                    price_change_h24 FLOAT,
                    social_mentions INTEGER,
                    rsi_14 FLOAT,
                    PRIMARY KEY (timestamp, token_address)
                );
                """))
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS trained_models (
                    model_name VARCHAR(50) PRIMARY KEY,
                    model_data BYTEA,
                    trained_at TIMESTAMP
                );
                """))
        logging.info("Database tables checked/created successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize DB: {e}", exc_info=True)

def save_model_to_db(model_name, model_object):
    """学習済みモデルをデータベースに保存する"""
    if not engine: return
    serialized_model = pickle.dumps(model_object)
    
    if engine.dialect.name == 'postgresql':
        stmt = text("""
        INSERT INTO trained_models (model_name, model_data, trained_at) VALUES (:name, :data, :ts)
        ON CONFLICT (model_name) DO UPDATE SET model_data = EXCLUDED.model_data, trained_at = EXCLUDED.trained_at;
        """)
    else: # SQLite
        stmt = text("""
        INSERT OR REPLACE INTO trained_models (model_name, model_data, trained_at) VALUES (:name, :data, :ts);
        """)

    with engine.connect() as conn:
        with conn.begin():
            conn.execute(stmt, {"name": model_name, "data": serialized_model, "ts": datetime.utcnow()})
    logging.info(f"Model '{model_name}' saved to database.")

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

def check_if_recently_notified(conn, token_address):
    """指定されたトークンが最近通知されたかチェックする"""
    query = text("SELECT last_notified FROM notification_history WHERE token_address = :addr")
    result = conn.execute(query, {"addr": token_address}).fetchone()
    if result and result[0]:
        last_notified_utc = result[0].replace(tzinfo=None)
        if (datetime.utcnow() - last_notified_utc).total_seconds() < NOTIFICATION_COOLDOWN_HOURS * 3600:
            return True
    return False

def record_notification(conn, token_addresses):
    """通知をDBに記録する"""
    if not isinstance(token_addresses, list): token_addresses = [token_addresses]
    if not token_addresses: return

    now_utc = datetime.utcnow()
    records = [{"addr": addr, "ts": now_utc} for addr in token_addresses]
    
    if engine.dialect.name == 'postgresql':
        stmt = text("""
        INSERT INTO notification_history (token_address, last_notified) VALUES (:addr, :ts)
        ON CONFLICT (token_address) DO UPDATE SET last_notified = EXCLUDED.last_notified;
        """)
    else: # SQLite
        stmt = text("""
        INSERT OR REPLACE INTO notification_history (token_address, last_notified) VALUES (:addr, :ts);
        """)
    conn.execute(stmt, records)

def insert_market_data_batch(conn, market_data_list):
    """現在の市場データ群を履歴テーブルに一括挿入する"""
    records = []
    now_utc = datetime.utcnow()
    for token in market_data_list:
        try:
            if not token.get('priceUsd') or not token.get('baseToken'): continue
            records.append({
                "ts": now_utc, "addr": token['baseToken']['address'], "price": float(token['priceUsd']),
                "vol": token.get('volume', {}).get('h24'), "h1": token.get('priceChange', {}).get('h1'),
                "h24": token.get('priceChange', {}).get('h24'), "mentions": token.get('social_data', {}).get('mentions'),
                "rsi": token.get('indicators', {}).get('rsi_14')
            })
        except (TypeError, KeyError): continue
    
    if not records: return
    stmt = text("""
    INSERT INTO market_data_history (timestamp, token_address, price_usd, volume_h24, price_change_h1, price_change_h24, social_mentions, rsi_14)
    VALUES (:ts, :addr, :price, :vol, :h1, :h24, :mentions, :rsi) ON CONFLICT (timestamp, token_address) DO NOTHING;
    """)
    conn.execute(stmt, records)
    if len(records) > 0:
        logging.info(f"Logged {len(records)} new records to market_data_history.")

def update_future_growth_labels(conn):
    """1時間前のデータに現在の価格を記録する"""
    now_utc = datetime.utcnow()
    target_time = now_utc - timedelta(hours=ML_LABEL_LOOKBACK_HOURS)
    time_window_start = target_time - timedelta(minutes=10)
    time_window_end = target_time + timedelta(minutes=10)
    
    query_tokens = text("""
    SELECT DISTINCT token_address FROM market_data_history 
    WHERE future_price_usd IS NULL AND timestamp BETWEEN :start AND :end
    """)
    tokens_to_update = conn.execute(query_tokens, {"start": time_window_start, "end": time_window_end}).fetchall()

    updates_for_db = []
    for (token_address,) in tokens_to_update:
        query_latest_price = text("SELECT price_usd FROM market_data_history WHERE token_address = :addr ORDER BY timestamp DESC LIMIT 1")
        current_record = conn.execute(query_latest_price, {"addr": token_address}).fetchone()
        
        if current_record:
            updates_for_db.append({
                "price": current_record[0], "addr": token_address,
                "start": time_window_start, "end": time_window_end
            })
    
    if updates_for_db:
        stmt_update = text("""
        UPDATE market_data_history SET future_price_usd = :price 
        WHERE token_address = :addr AND future_price_usd IS NULL AND timestamp BETWEEN :start AND :end
        """)
        result = conn.execute(stmt_update, updates_for_db)
        if result.rowcount > 0:
            logging.info(f"Updated {result.rowcount} future price labels in history table.")
