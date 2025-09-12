# database.py (修正後のフルコード)
import sqlite3
import logging
from config import DB_FILE, DATABASE_URL

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    """データベース接続を取得する"""
    if DATABASE_URL:
        # PostgreSQLの場合 (Render)
        # SQLAlchemyやpsycopg2のようなライブラリを使用する必要があります
        # このサンプルではSQLiteをエミュレートするが、本番では適切なDB接続に置き換える
        logging.warning("DATABASE_URL is set, but this simple example uses SQLite. "
                        "For production with PostgreSQL, use a proper ORM/driver.")
        return sqlite3.connect(DB_FILE) # ローカルテスト用に引き続きSQLiteを使用
    else:
        # SQLiteの場合
        return sqlite3.connect(DB_FILE)

def init_db():
    """データベースを初期化し、必要なテーブルを作成する"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # オープンポジションテーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS open_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            amount REAL NOT NULL,
            entry_price REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # トレード履歴テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            amount REAL NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            pnl REAL,
            status TEXT NOT NULL, -- 'open' or 'closed'
            open_time DATETIME NOT NULL,
            close_time DATETIME
        )
    ''')
    
    # ✅ 追加: シグナルログテーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            token_address TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL, -- 'long' or 'short'
            ai_confidence REAL NOT NULL,
            price_usd REAL NOT NULL,
            decision TEXT NOT NULL, -- 'Approved' or 'Rejected'
            rejection_reason TEXT -- 拒否された場合のみ理由を記録
        )
    ''')


    conn.commit()
    conn.close()
    logging.info("Database initialized.")

def log_trade_open(symbol, side, amount, entry_price):
    """オープンポジションとトレード履歴に新しいトレードを記録する"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('INSERT INTO open_positions (symbol, side, amount, entry_price) VALUES (?, ?, ?, ?)',
                   (symbol, side, amount, entry_price))
    
    cursor.execute('INSERT INTO trade_history (symbol, side, amount, entry_price, status, open_time) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)',
                   (symbol, side, amount, entry_price, 'open'))
    
    conn.commit()
    conn.close()
    logging.info(f"Trade opened: {side} {amount} of {symbol} at {entry_price}")

def log_trade_close(symbol, exit_price, pnl):
    """オープンポジションを閉じ、トレード履歴を更新する"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # オープンポジションを取得
    cursor.execute('SELECT id, amount, entry_price, side FROM open_positions WHERE symbol = ?', (symbol,))
    position = cursor.fetchone()

    if position:
        pos_id, amount, entry_price, side = position
        
        # オープンポジションを削除
        cursor.execute('DELETE FROM open_positions WHERE id = ?', (pos_id,))
        
        # トレード履歴を更新
        cursor.execute('''
            UPDATE trade_history
            SET exit_price = ?, pnl = ?, status = ?, close_time = CURRENT_TIMESTAMP
            WHERE symbol = ? AND status = 'open'
        ''', (exit_price, pnl, 'closed', symbol))
        
        conn.commit()
        logging.info(f"Trade closed: {symbol} at {exit_price}. PnL: {pnl}")
    else:
        logging.warning(f"No open position found for {symbol} to close.")
    
    conn.close()

def get_open_position():
    """現在開いているポジションを一つ取得する (単一ポジション戦略用)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT symbol, side, amount, entry_price FROM open_positions LIMIT 1')
    position = cursor.fetchone()
    conn.close()
    
    if position:
        return {'symbol': position[0], 'side': position[1], 'amount': position[2], 'entry_price': position[3]}
    return None

# ✅ 追加: シグナルログを記録する関数
def log_signal_decision(token_address, symbol, signal_type, ai_confidence, price_usd, decision, rejection_reason=None):
    """AIシグナルと戦略の決定をログに記録する"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO signal_logs (token_address, symbol, signal_type, ai_confidence, price_usd, decision, rejection_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (token_address, symbol, signal_type, ai_confidence, price_usd, decision, rejection_reason))
    
    conn.commit()
    conn.close()
    logging.info(f"Signal Logged: {symbol} ({signal_type}) - AI: {ai_confidence:.1%} - Decision: {decision}" + (f" ({rejection_reason})" if rejection_reason else ""))

# データベース初期化を忘れずに呼び出す
init_db()

