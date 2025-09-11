import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("7904380124:AAE2AuRITmgBw5OECTELF5151D3pRz4K9JM")
TELEGRAM_CHAT_ID = os.getenv("5890119671")

# --- Database ---
DB_FILE = "sentinel_data.db"
MODEL_FILE = 'trend_classifier.joblib'

# --- System Logic ---
NOTIFICATION_COOLDOWN_HOURS = 6
ML_LABEL_LOOKBACK_HOURS = 1
ML_PRICE_GROWTH_THRESHOLD = 0.10