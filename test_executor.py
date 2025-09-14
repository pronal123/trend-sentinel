import pandas as pd
from trading_executor import TradingExecutor
from state_manager import StateManager
from telegram_notifier import TelegramNotifier

state = StateManager()
executor = TradingExecutor(state)
notifier = TelegramNotifier()

# Spot LONG テスト
try:
    print("=== Spot LONG test ===")
    df = pd.DataFrame({"close":[40000]})
    executor.open_position("LONG", "BTC/USDT", df, 80, notifier, "Spotテスト", 100, market_type="spot")
except Exception as e:
    print("Spotテスト失敗:", e)

# Futures SHORT テスト
try:
    print("=== Futures SHORT test ===")
    df = pd.DataFrame({"close":[40000]})
    executor.open_position("SHORT", "BTC/USDT:USDT", df, 80, notifier, "Futuresテスト", 100, market_type="futures")
except Exception as e:
    print("Futuresテスト失敗:", e)
