import os

# Trading / infrastructure
PAPER_TRADING_ENABLED = os.getenv("PAPER_TRADING", "true").lower() in ("1","true","yes")
EXCHANGE_ID = "bitget"
EXCHANGE_API_KEY = os.getenv("BITGET_API_KEY")
EXCHANGE_SECRET_KEY = os.getenv("BITGET_SECRET_KEY")
EXCHANGE_API_PASSPHRASE = os.getenv("BITGET_PASSPHRASE", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# External APIs
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")  # for English news (optional)
COVALENT_API_KEY = os.getenv("COVALENT_API_KEY")  # on-chain (optional)
FNG_URL = os.getenv("ALTERNATIVE_FNG_API_URL", "https://api.alternative.me/fng/")

# Bot params
MONITORED_CHAINS = os.getenv("MONITORED_CHAINS", "ethereum,solana,base,bnb,arbitrum,optimism,polygon,avalanche").split(",")
TRADING_CYCLE_TIMES = os.getenv("TRADING_CYCLE_TIMES", "02:00,08:00,14:00,20:00").split(",")
DAILY_SUMMARY_TIME = os.getenv("NOTIFY_DAILY_TIME", "21:00")
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
CANDIDATE_POOL_SIZE = int(os.getenv("CANDIDATE_POOL_SIZE", "50"))

# Strategy thresholds (as described)
LONG_RULE = {"24h": 12.0, "1h": 5.0, "volume_pct": 150.0}
SHORT_RULE = {"24h": -8.0, "1h": -3.0, "volume_pct": 200.0}
SPIKE_RULE = {"1h": 8.0, "15m_volume_mult": 3.0}

# Persistence
STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
