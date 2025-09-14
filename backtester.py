import yfinance as yf
import pandas as pd
import logging
from data_aggregator import DataAggregator


class Backtester:
    def __init__(self, symbol="BTC-USD", interval="5m", period="30d"):
        self.symbol = symbol
        self.interval = interval
        self.period = period
        self.aggregator = DataAggregator()

    def run_backtest(self):
        logging.info(f"Starting backtest for {self.symbol} ({self.period}, {self.interval})")

        df = yf.download(self.symbol, period=self.period, interval=self.interval)
        if df.empty:
            logging.error("No historical data fetched.")
            return {}

        trades = []
        balance = 10000.0  # 初期残高（USD）
        position = None

        for i in range(2, len(df)):
            row = df.iloc[i]
            price = row["Close"]

            # ポジション未保有ならシグナルをチェック
            if position is None:
                change_1h = (df["Close"].iloc[i] / df["Close"].iloc[i-12] - 1) * 100  # 1h変動
                change_24h = (df["Close"].iloc[i] / df["Close"].iloc[i-288] - 1) * 100 if i >= 288 else 0

                # 簡易ロジック: 24h +5%以上 & 1h +2%以上 ならロング
                if change_24h > 5 and change_1h > 2:
                    tp, sl = self.aggregator.calc_takeprofit_stoploss(price, 0.1)
                    position = {"side": "long", "entry": price, "tp": tp, "sl": sl}
                    logging.info(f"LONG entry at {price}, TP={tp}, SL={sl}")

                # 24h -5%以下 & 1h -2%以下 ならショート
                elif change_24h < -5 and change_1h < -2:
                    tp, sl = self.aggregator.calc_takeprofit_stoploss(price, -0.1)
                    position = {"side": "short", "entry": price, "tp": tp, "sl": sl}
                    logging.info(f"SHORT entry at {price}, TP={tp}, SL={sl}")

            else:
                # ポジション保有中 → 利確 / 損切チェック
                if position["side"] == "long":
                    if price >= position["tp"]:
                        profit = (position["tp"] - position["entry"])
                        balance += profit
                        trades.append({"side": "long", "result": "win", "profit": profit})
                        position = None
                    elif price <= position["sl"]:
                        loss = (position["sl"] - position["entry"])
                        balance += loss
                        trades.append({"side": "long", "result": "loss", "profit": loss})
                        position = None

                elif position["side"] == "short":
                    if price <= position["tp"]:
                        profit = (position["entry"] - position["tp"])
                        balance += profit
                        trades.append({"side": "short", "result": "win", "profit": profit})
                        position = None
                    elif price >= position["sl"]:
                        loss = (position["entry"] - position["sl"])
                        balance += loss
                        trades.append({"side": "short", "result": "loss", "profit": loss})
                        position = None

        # 集計
        df_trades = pd.DataFrame(trades)
        win_rate = (df_trades["result"] == "win").mean() * 100 if not df_trades.empty else 0
        total_profit = df_trades["profit"].sum() if not df_trades.empty else 0

        summary = {
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "final_balance": round(balance, 2),
            "total_profit": round(total_profit, 2),
        }

        logging.info(f"Backtest finished. Summary: {summary}")
        df_trades.to_csv("backtest_trades.csv", index=False)

        return summary
