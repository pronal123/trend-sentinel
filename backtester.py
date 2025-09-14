import yfinance as yf
import pandas as pd
import logging
from data_aggregator import DataAggregator


class Backtester:
    def __init__(self, symbols=None, interval="5m", period="30d"):
        if symbols is None:
            symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]
        self.symbols = symbols
        self.interval = interval
        self.period = period
        self.aggregator = DataAggregator()

    def run_backtest_for_symbol(self, symbol):
        logging.info(f"Starting backtest for {symbol} ({self.period}, {self.interval})")

        df = yf.download(symbol, period=self.period, interval=self.interval)
        if df.empty:
            logging.error(f"No historical data fetched for {symbol}.")
            return {}

        trades = []
        balance = 10000.0  # 初期残高（USD）
        position = None

        for i in range(2, len(df)):
            row = df.iloc[i]
            price = row["Close"]

            # ポジション未保有ならシグナルをチェック
            if position is None:
                change_1h = (df["Close"].iloc[i] / df["Close"].iloc[i-12] - 1) * 100 if i >= 12 else 0
                change_24h = (df["Close"].iloc[i] / df["Close"].iloc[i-288] - 1) * 100 if i >= 288 else 0

                if change_24h > 5 and change_1h > 2:
                    tp, sl = self.aggregator.calc_takeprofit_stoploss(price, 0.1)
                    position = {"side": "long", "entry": price, "tp": tp, "sl": sl}

                elif change_24h < -5 and change_1h < -2:
                    tp, sl = self.aggregator.calc_takeprofit_stoploss(price, -0.1)
                    position = {"side": "short", "entry": price, "tp": tp, "sl": sl}

            else:
                if position["side"] == "long":
                    if price >= position["tp"]:
                        profit = position["tp"] - position["entry"]
                        balance += profit
                        trades.append({"symbol": symbol, "side": "long", "result": "win", "profit": profit})
                        position = None
                    elif price <= position["sl"]:
                        loss = position["sl"] - position["entry"]
                        balance += loss
                        trades.append({"symbol": symbol, "side": "long", "result": "loss", "profit": loss})
                        position = None

                elif position["side"] == "short":
                    if price <= position["tp"]:
                        profit = position["entry"] - position["tp"]
                        balance += profit
                        trades.append({"symbol": symbol, "side": "short", "result": "win", "profit": profit})
                        position = None
                    elif price >= position["sl"]:
                        loss = position["entry"] - position["sl"]
                        balance += loss
                        trades.append({"symbol": symbol, "side": "short", "result": "loss", "profit": loss})
                        position = None

        df_trades = pd.DataFrame(trades)
        win_rate = (df_trades["result"] == "win").mean() * 100 if not df_trades.empty else 0
        total_profit = df_trades["profit"].sum() if not df_trades.empty else 0

        summary = {
            "symbol": symbol,
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "final_balance": round(balance, 2),
            "total_profit": round(total_profit, 2),
        }

        df_trades.to_csv(f"backtest_{symbol.replace('-','_')}.csv", index=False)
        return summary

    def run_all(self):
        results = []
        for symbol in self.symbols:
            res = self.run_backtest_for_symbol(symbol)
            if res:
                results.append(res)

        df_results = pd.DataFrame(results)
        if not df_results.empty:
            overall = {
                "symbol": "ALL",
                "total_trades": df_results["total_trades"].sum(),
                "win_rate": round(df_results["win_rate"].mean(), 2),
                "final_balance": round(df_results["final_balance"].mean(), 2),
                "total_profit": round(df_results["total_profit"].sum(), 2),
            }
            results.append(overall)

        pd.DataFrame(results).to_csv("backtest_summary.csv", index=False)
        return results
