import numpy as np
import pandas as pd
import logging

class Backtester:
    def __init__(self, ohlcv, fee_rate=0.0006, slippage_pct=0.0005):
        self.df = pd.DataFrame(ohlcv, columns=["ts","o","h","l","c","v"])
        self.df["ts"] = pd.to_datetime(self.df["ts"], unit="ms")
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct

    def run(self):
        returns = []
        for i in range(15, len(self.df)):
            entry = self.df.iloc[i-1]["c"]
            exit = self.df.iloc[i]["c"]
            side = np.random.choice(["long","short"])  # placeholder rule
            pnl = (exit-entry) if side=="long" else (entry-exit)

            # apply slippage and fees
            pnl -= entry * (self.fee_rate + self.slippage_pct)
            returns.append(pnl/entry)

        if len(returns) == 0:
            return {"winrate":0,"sharpe":0,"pf":0}

        returns = np.array(returns)
        winrate = (returns>0).mean()*100
        sharpe = np.mean(returns)/ (np.std(returns)+1e-8) * np.sqrt(252)
        pf = returns[returns>0].sum() / abs(returns[returns<0].sum() + 1e-8)

        logging.info(f"Backtest result: winrate={winrate:.1f} sharpe={sharpe:.2f} pf={pf:.2f}")
        return {"winrate":winrate,"sharpe":sharpe,"pf":pf}
