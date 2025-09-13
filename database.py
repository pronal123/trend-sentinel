import sqlite3
import logging
from datetime import datetime, timedelta

# config.pyからインポートすることを想定
# from config import DB_FILE, NOTIFICATION_COOLDOWN_HOURS, ML_LABEL_LOOKBACK_HOURS
# 以下はハードコードした仮の値
DB_FILE = "sentinel_data.db"
NOTIFICATION_COOLDOWN_HOURS = 6
ML_LABEL_LOOKBACK_HOURS = 1


def init_db():
    """データベースとテーブルを初期化する"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        
        # 通知履歴テーブル
        conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_history (
            token_address TEXT PRIMARY KEY, 
            last_notified TEXT NOT NULL
        )""")
        
        # ML用データ履歴テーブル
        conn.execute("""
        CREATE TABLE IF NOT EXISTS market_data_history (
            timestamp TEXT, 
            token_address TEXT, 
            price_usd REAL, 
            volume_h24 REAL,
            price_change_h1 REAL, 
            price_change_h24 REAL, 
            social_mentions INTEGER,
            future_price_grew INTEGER, 
            PRIMARY KEY (timestamp, token_address)
        )""")

        # 現在開いているポジションを管理するテーブル
        conn.execute("""
        CREATE TABLE IF NOT EXISTS open_positions (
            symbol TEXT PRIMARY KEY,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            amount REAL NOT NULL,
            opened_at TEXT NOT NULL
        )""")
        
        # 全ての取引履歴を記録するテーブル
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL, -- 'OPEN' or 'CLOSE'
            price REAL NOT NULL,
            amount REAL NOT NULL,
            timestamp TEXT NOT NULL
        )""")
        
        # 分析シグナルの最終決定を記録するテーブル
        conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL, -- 'LONG' or 'SHORT'
            decision TEXT NOT NULL, -- 'ENTER', 'PASS', 'CLOSE'など
            reason TEXT
        )""")

    logging.info("Database initialized successfully.")

def check_if_recently_notified(conn, token_address):
    """指定されたトークンが最近通知されたかチェックする"""
    cursor = conn.cursor()
    cursor.execute("SELECT last_notified FROM notification_history WHERE token_address = ?", (token_address,))
    result = cursor.fetchone()
    if result and result[0]:
        last_notified = datetime.fromisoformat(result[0])
        if (datetime.now() - last_notified).total_seconds() < NOTIFICATION_COOLDOWN_HOURS * 3600:
            return True
    return False

def record_notification(conn, token_address):
    """通知をDBに記録する"""
    conn.execute(
        "INSERT OR REPLACE INTO notification_history (token_address, last_notified) VALUES (?, ?)",
        (token_address, datetime.now().isoformat())
    )

def insert_market_data_batch(conn, market_data_list):
    """現在の市場データ群を履歴テーブルに一括挿入する"""
    records_to_insert = []
    now_iso = datetime.now().isoformat()
    for token in market_data_list:
        try:
            if not token.get('priceUsd') or not token.get('baseToken'): continue
            records_to_insert.append((
                now_iso,
                token['baseToken']['address'],
                float(token['priceUsd']),
                token.get('volume', {}).get('h24'),
                token.get('priceChange', {}).get('h1'),
                token.get('priceChange', {}).get('h24'),
                token.get('social_data', {}).get('mentions')
            ))
        except (TypeError, KeyError) as e:
            logging.warning(f"Skipping record due to malformed data for {token.get('baseToken', {}).get('symbol')}: {e}")

    if not records_to_insert: return
    with conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO market_data_history (timestamp, token_address, price_usd, volume_h24, price_change_h1, price_change_h24, social_mentions)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, token_address) DO NOTHING;
        """, records_to_insert)
        if cursor.rowcount > 0:
            logging.info(f"Logged {cursor.rowcount} new records to market_data_history.")

def update_future_growth_labels(conn, current_market_data):
    """現在の価格を使い、過去のデータにML用の結果ラベルを書き込む"""
    current_price_map = {
        token['baseToken']['address']: float(token['priceUsd'])
        for token in current_market_data if token.get('priceUsd') and token.get('baseToken')
    }
    if not current_price_map: return

    target_time = datetime.now() - timedelta(hours=ML_LABEL_LOOKBACK_HOURS)
    time_window_start = (target_time - timedelta(minutes=5)).isoformat()
    time_window_end = (target_time + timedelta(minutes=5)).isoformat()

    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, token_address, price_usd FROM market_data_history
            WHERE future_price_grew IS NULL AND timestamp BETWEEN ? AND ?
        """, (time_window_start, time_window_end))
        records_to_update = cursor.fetchall()

        updates_for_db = []
        for timestamp, token_address, old_price in records_to_update:
            if token_address in current_price_map and old_price and old_price > 0:
                current_price = current_price_map[token_address]
                price_growth = (current_price - old_price) / old_price
                future_price_grew = 1 if price_growth > 0.10 else 0
                updates_for_db.append((future_price_grew, timestamp, token_address))

        if updates_for_db:
            cursor.executemany("UPDATE market_data_history SET future_price_grew = ? WHERE timestamp = ? AND token_address = ?", updates_for_db)
            if cursor.rowcount > 0:
                logging.info(f"Updated {cursor.rowcount} ML labels in history table.")

def get_open_position(conn, symbol):
    """指定されたシンボルのオープンポジションを取得する"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM open_positions WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    if row:
        keys = [description[0] for description in cursor.description]
        return dict(zip(keys, row))
    return None

def log_trade_open(conn, symbol, side, price, amount):
    """ポジションを開いたことをDBに記録する"""
    timestamp = datetime.now().isoformat()
    with conn:
        conn.execute(
            "INSERT INTO open_positions (symbol, side, entry_price, amount, opened_at) VALUES (?, ?, ?, ?, ?)",
            (symbol, side, price, amount, timestamp)
        )
        conn.execute(
            "INSERT INTO trade_history (symbol, side, status, price, amount, timestamp) VALUES (?, ?, 'OPEN', ?, ?, ?)",
            (symbol, side, price, amount, timestamp)
        )
    logging.info(f"OPENED position: {side} {amount} {symbol} @ {price}")

def log_trade_close(conn, symbol, price, amount):
    """ポジションを閉じたことをDBに記録する"""
    timestamp = datetime.now().isoformat()
    with conn:
        position = get_open_position(conn, symbol)
        if not position:
            logging.warning(f"Attempted to close a position that does not exist: {symbol}")
            return
        side = position['side']
        
        conn.execute("DELETE FROM open_positions WHERE symbol = ?", (symbol,))
        conn.execute(
            "INSERT INTO trade_history (symbol, side, status, price, amount, timestamp) VALUES (?, ?, 'CLOSE', ?, ?, ?)",
            (symbol, side, price, amount, timestamp)
        )
    logging.info(f"CLOSED position: {side} {amount} {symbol} @ {price}")

def log_signal_decision(conn, symbol, signal_type, decision, reason=""):
    """分析シグナルの最終決定をDBに記録する"""
    timestamp = datetime.now().isoformat()
    with conn:
        conn.execute(
            "INSERT INTO signal_decisions (timestamp, symbol, signal_type, decision, reason) VALUES (?, ?, ?, ?, ?)",
            (timestamp, symbol, signal_type, decision, reason)
        )
    logging.info(f"DECISION LOGGED: {symbol} | {signal_type} -> {decision} | Reason: {reason}")
