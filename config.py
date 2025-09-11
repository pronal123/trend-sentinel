import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Database ---
DB_FILE = "sentinel_data.db"
# ✅ 修正点: RenderのデータベースURLを読み込む
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Machine Learning ---
MODEL_FILE = 'trend_classifier'
# ✅ 修正点: Render上で学習をトリガーするための秘密キーを読み込む
TRAIN_SECRET_KEY = os.getenv("TRAIN_SECRET_KEY")


# --- System Logic ---
NOTIFICATION_COOLDOWN_HOURS = 6
ML_LABEL_LOOKBACK_HOURS = 1
ML_PRICE_GROWTH_THRESHOLD = 0.10
PROXY_URL = os.getenv("PROXY_URL")
