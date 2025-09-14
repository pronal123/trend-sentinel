# config.py
import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む (ローカルでの開発用)
load_dotenv()

# --- 1. BOTの基本動作設定 (Core Bot Behavior) ---
# BOTの取引機能を有効にするか (true/false)
IS_BOT_ACTIVE = os.getenv("BOT_ACTIVE", "true").lower() in ("true", "1", "yes")

# 先物取引（ショート取引を含む）を有効にするか (true/false)
ENABLE_FUTURES_TRADING = os.getenv("ENABLE_FUTURES_TRADING", "true").lower() in ("true", "1", "yes")

# シミュレーションモード（実際には注文しない）を有効にするか (true/false)
PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"

# 最大同時保有ポジション数
MAX_OPEN_POSITIONS = 3

# 同じトークンに関する通知のクールダウン期間 (時間)
NOTIFICATION_COOLDOWN_HOURS = 6

# --- 2. スケジュール設定 (JST) ---
# 定期的な取引サイクルを実行する時刻
TRADING_CYCLE_TIMES = ["02:00", "08:00", "14:00", "20:00"]

# 日次サマリーを通知する時刻
DAILY_SUMMARY_TIME = "21:00"

# --- 3. 外部サービス接続設定 (External Service Connections) ---
# データベース設定
DATABASE_URL = os.getenv("DATABASE_URL")  # RenderなどのPostgreSQL用URL

# 取引所設定
EXCHANGE_ID = os.getenv("EXCHANGE_ID", "bitget")
EXCHANGE_MARKET_TYPE = 'swap' if ENABLE_FUTURES_TRADING else 'spot' # 先物設定に応じて自動切り替え
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_SECRET_KEY")
EXCHANGE_API_PASSPHRASE = os.getenv("EXCHANGE_API_PASSPHRASE")

# Telegram通知設定
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- 4. 取引戦略パラメータ (Trading Strategy Parameters) ---
# スコアリングとエントリー閾値
ENTRY_SCORE_THRESHOLD_TRENDING = 70  # トレンド相場での最低取引スコア
ENTRY_SCORE_THRESHOLD_RANGING = 80   # レンジ相場での最低取引スコア
CANDIDATE_POOL_SIZE = 3              # 一度に詳細分析する候補数 (ロング/ショートそれぞれ)
ADX_THRESHOLD = 25                   # トレンド/レンジ相場を判断するADXの閾値

# ポジションサイズ設定 (USD)
BASE_POSITION_SIZE_USD = 50.0   # 最低取引額
MAX_POSITION_SIZE_USD = 250.0 # 最高取引額

# リスク管理設定 (ATRベース)
ATR_STOP_LOSS_MULTIPLIER = 1.5   # ATR x 1.5 を損切りラインに
ATR_TAKE_PROFIT_MULTIPLIER = 3.0 # ATR x 3.0 を利食いラインに

# 市場分析の対象
MARKET_CONTEXT_TICKER = 'BTC-USD' # 市場全体の状況判断に使うティッカー
