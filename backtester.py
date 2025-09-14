import pandas as pd
import numpy as np
import logging
import matplotlib.pyplot as plt

class Backtester:
    def __init__(self, initial_balance=10000):
        self.balance = initial_balance
        self.trades = []

    def calculate_atr(self, df: pd.DataFrame, period=14):
        if len(df) < period:
            return None
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        tr = pd.concat([
            high - low,
            (high - close).abs(),
            (low - close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def run(self, df: pd.DataFrame, symbol: str, side: str):
        logging.info(f"バックテスト開始: {symbol} {side}")
        for i in range(30, len(df)):
            subset = df.iloc[:i].copy()
            atr = self.calculate_atr(subset)
            if atr is None or np.isnan(atr):
                continue

            entry_price = df.iloc[i]['close']
            if side == "LONG":
                take_profit = entry_price + atr * 2
                stop_loss = entry_price - atr
            else:
                take_profit = entry_price - atr * 2
                stop_loss = entry_price + atr

            outcome = None
            exit_price = None

            for j in range(i+1, len(df)):
                high = df.iloc[j]['high']
                low = df.iloc[j]['low']
                if side == "LONG":
                    if low <= stop_loss:
                        outcome = "LOSS"
                        exit_price = stop_loss
                        break
                    elif high >= take_profit:
                        outcome = "WIN"
                        exit_price = take_profit
                        break
                else:
                    if high >= stop_loss:
                        outcome = "LOSS"
                        exit_price = stop_loss
                        break
                    elif low <= take_profit:
                        outcome = "WIN"
                        exit_price = take_profit
                        break

            if outcome:
                pnl = (exit_price - entry_price) if side == "LONG" else (entry_price - exit_price)
                self.balance += pnl
                self.trades.append({
                    "symbol": symbol,
                    "side": side,
                    "entry": entry_price,
                    "exit": exit_price,
                    "outcome": outcome,
                    "pnl": pnl,
                    "balance": self.balance
                })

        return pd.DataFrame(self.trades)

    def summary(self):
        df = pd.DataFrame(self.trades)
        if df.empty:
            return {"win_rate": 0, "trades": 0, "final_balance": self.balance}
        win_rate = (df['outcome'] == "WIN").mean() * 100
        return {
            "win_rate": round(win_rate, 2),
            "trades": len(df),
            "final_balance": round(self.balance, 2)
        }
