# config.py
import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む (ローカルでの開発用)
load_dotenv()

# --- 1. BOTの基本動作設定 (Core Bot Behavior) ---
IS_BOT_ACTIVE = os.getenv("BOT_ACTIVE", "true").lower() in ("true", "1", "yes")
PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true" # trueでテスト/シミュレーションモード
MAX_OPEN_POSITIONS = 3  # 最大同時保有ポジション数
NOTIFICATION_COOLDOWN_HOURS = 6 # 同じトークンに関する通知のクールダウン期間 (時間)

# --- 2. スケジュール設定 (JST) ---
TRADING_CYCLE_TIMES = ["02:00", "08:00", "14:00", "20:00"] # 6時間ごとの取引サイクル
DAILY_SUMMARY_TIME = "21:00" # 日次サマリーの通知時刻

# --- 3. 外部サービス接続設定 (External Service Connections) ---
# データベース設定
DB_FILE = "app.db" # SQLiteデータベースファイル名 (ローカル用)
DATABASE_URL = os.getenv("DATABASE_URL") # RenderなどのPostgreSQL用URL

# 取引所設定 (ccxt)
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "bitget")
EXCHANGE_MARKET_TYPE = os.getenv("EXCHANGE_MARKET_TYPE", "swap") # 'spot' (現物) or 'swap' (先物)
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_SECRET_KEY")
EXCHANGE_API_PASSPHRASE = os.getenv("EXCHANGE_API_PASSPHRASE")

# Telegram通知設定
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 外部APIキー
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY") # オンチェーン分析用 (オプション)

# プロキシ設定 (必要に応じて)
PROXY_URL = os.getenv("PROXY_URL")

# --- 4. 取引戦略パラメータ (Trading Strategy Parameters) ---
# スコアリングとエントリー閾値
ENTRY_SCORE_THRESHOLD_TRENDING = 70  # トレンド相場での最低取引スコア
ENTRY_SCORE_THRESHOLD_RANGING = 80   # レンジ相場での最低取引スコア
CANDIDATE_POOL_SIZE = 3              # 一度に詳細分析する候補数 (ロング/ショートそれぞれ)
ADX_THRESHOLD = 25                   # トレンド/レンジ相場を判断するADXの閾値

# ポジションサイズ設定
# スコアに応じて動的にサイズを決定する方式
BASE_POSITION_SIZE_USD = 50.0   # 最低取引額
MAX_POSITION_SIZE_USD = 250.0 # 最高取引額

# リスク管理設定
# ATRベースの動的SL/TPと、固定パーセンテージベースのどちらを使うか trading_executor.py で選択
ATR_STOP_LOSS_MULTIPLIER = 1.5   # ATR x 1.5 を損切りラインに
ATR_TAKE_PROFIT_MULTIPLIER = 3.0 # ATR x 3.0 を利食いラインに

FIXED_STOP_LOSS_PERCENT = 0.05   # 5%の損失で損切り
FIXED_TAKE_PROFIT_PERCENT = 0.10 # 10%の利益で利食い

# 市場分析の対象
MARKET_CONTEXT_TICKER = 'BTC-USD' # 市場全体の状況判断に使うティッカー

# --- 5. 機械学習モデル設定 (Machine Learning Model Settings) ---
MODEL_DIR = "ml_models" # モデルを保存するディレクトリ
# os.path.joinを使い、OSに依存しない安全なパスを作成
MODEL_PATH = os.path.join(MODEL_DIR, "sentiment_model.joblib")
TRAIN_SECRET_KEY = os.getenv("TRAIN_SECRET_KEY", "your_strong_secret_key_here") # モデル再学習用シークレットキー

# ラベル付けの閾値
ML_PRICE_GROWTH_THRESHOLD = 0.02 # 2%以上の価格変化を'up'/'down'と判断
ML_LABEL_LOOKBACK_HOURS = 1      # 1時間後の価格を見てラベルを生成

