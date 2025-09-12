import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Database ---
# ✅ 修正点: 削除されていたDB_FILEの定義を復活
DB_FILE = "sentinel_data.db"
DATABASE_URL = os.getenv("DATABASE_URL")

# --- External APIs ---
PROXY_URL = os.getenv("PROXY_URL")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")

# --- Exchange Settings ---
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_API_SECRET")
PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "True").lower() in ('true', '1', 't')

# --- Machine Learning ---
MODEL_FILE = 'trend_classifier'
TRAIN_SECRET_KEY = os.getenv("TRAIN_SECRET_KEY")
MODEL_PATH = os.getenv("MODEL_PATH", ".")

# --- Advanced Strategy Parameters ---
ADX_THRESHOLD = 25
POSITION_RISK_PERCENT = 0.1
STOP_LOSS_PERCENT = 0.05
TAKE_PROFIT_PERCENT = 0.10
AI_CONFIDENCE_THRESHOLD = 0.80

# --- System Logic ---
NOTIFICATION_COOLDOWN_HOURS = 6
ML_LABEL_LOOKBACK_HOURS = 1
ML_PRICE_GROWTH_THRESHOLD = 0.10
