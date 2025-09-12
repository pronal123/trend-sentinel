import os

# --- General Settings ---
DB_FILE = "app.db" # SQLiteデータベースファイル名 (ローカル用)
DATABASE_URL = os.getenv("DATABASE_URL") # RenderなどのPostgreSQL用URL

# --- Exchange Settings ---
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "bitget")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_API_SECRET")
EXCHANGE_API_PASSPHRASE = os.getenv("EXCHANGE_API_PASSPHRASE") # Bitgetなど一部の取引所に必要

PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true" # "true"でテストネット有効

# --- API Keys ---
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Proxy Settings (if needed) ---
PROXY_URL = os.getenv("PROXY_URL") # 例: "http://your_proxy_ip:port"

# --- Advanced Strategy Parameters ---
ADX_THRESHOLD = 25
POSITION_RISK_PERCENT = 0.1 # 総資産の10%をリスクに晒す
STOP_LOSS_PERCENT = 0.05 # 5%の損失で損切り
TAKE_PROFIT_PERCENT = 0.10 # 10%の利益で利確
AI_CONFIDENCE_THRESHOLD = 0.70 # AIの確信度が70%以上でエントリーを検討

# --- System Logic ---
NOTIFICATION_COOLDOWN_HOURS = 6 # 同じトークンに関する通知のクールダウン期間 (時間)
ML_LABEL_LOOKBACK_HOURS = 1 # MLモデルのラベルを生成する際の未来の価格変化を見る時間 (例: 1時間後の価格)
ML_PRICE_GROWTH_THRESHOLD = 0.02 # MLモデルで'up'/'down'と判断する価格変化の閾値 (例: 2%以上の価格変化)

# --- ML Model Settings ---
MODEL_DIR = "ml_models" # モデルを保存するディレクトリ
MODEL_PATH = os.path.join(MODEL_DIR, "sentiment_model.joblib") # ✅ 修正: ディレクトリとファイル名を結合
TRAIN_SECRET_KEY = os.getenv("TRAIN_SECRET_KEY", "your_strong_secret_key_here") # モデル再学習用シークレットキー

