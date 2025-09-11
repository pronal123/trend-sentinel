# config.py (修正後のフルコード)
import os
from dotenv import load_dotenv

load_dotenv()

# --- Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DATABASE_URL = os.getenv("DATABASE_URL")
PROXY_URL = os.getenv("PROXY_URL")
MODEL_FILE = 'trend_classifier'
TRAIN_SECRET_KEY = os.getenv("TRAIN_SECRET_KEY")
MODEL_PATH = os.getenv("MODEL_PATH", ".")

# --- ✅ 修正点: Moralis API Key ---
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")

# --- System Logic ---
NOTIFICATION_COOLDOWN_HOURS = 6
ML_LABEL_LOOKBACK_HOURS = 1
ML_PRICE_GROWTH_THRESHOLD = 0.10
