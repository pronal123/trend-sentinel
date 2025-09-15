# backtester.py
import numpy as np
from typing import List, Tuple
import math


class Backtester:
    """
    シンプルなルールを過去OHLCVに適用してトレード1000回相当のパフォーマンスを算出するモジュール。
    - 入退出ルールは main.py のルールに合わせる（ここは簡易実装）
    """

    def __init__(self, ohlcv: List[List[float]]):
        """
        ohlcv: list of [ts, open, high, low, close, volume]
        """
        self.ohlcv = ohlcv

    def run_rule_sim(self, atr_period=14, tp_mult=2.0, sl_mult=1.0, position_usd=100.0, initial_balance=10000.0) -> dict:
        """
        単純バックテスト：
         - シンプル指標：1日（あるいは与えられたtf）で前日比が閾値を満たせばエントリー（ここは main と呼応）
         - TP/SL は ATR に基づく固定倍率
        """
        n = len(self.ohlcv)
        if n < atr_period + 2:
            return {}

        # convert closes
        closes = [row[4] for row in self.ohlcv]
        highs = [row[2] for row in self.ohlcv]
        lows = [row[3] for row in self.ohlcv]

        # calc ATR rolling
        trs = []
        for i in range(1, n):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        atrs = []
        for i in range(atr_period, len(trs)):
            atrs.append(sum(trs[i-atr_period:i]) / atr_period)

        balance = initial_balance
        eq_curve = []
        trades = []

        # iterate but ensure index alignment
        for i in range(atr_period + 1, n - 1):
            price = closes[i]
            prev = closes[i-1]
            # simple momentum signal
            change_pct = (price / prev - 1) * 100.0
            atr = atrs[i - (atr_period + 1)] if (i - (atr_period + 1)) < len(atrs) and (i - (atr_period + 1)) >= 0 else None
            if atr is None:
                continue
            # entry rules (example): strong 1-step momentum
            if change_pct > 5.0:
                # long
                entry = price
                tp = entry + tp_mult * atr
                sl = entry - sl_mult * atr
                # simulate next bars until hit TP or SL or close at next bar close
                pnl = 0.0
                for j in range(i+1, min(n, i+100)):  # look ahead
                    high = highs[j]; low = lows[j]; close_j = closes[j]
                    if low <= sl:
                        pnl = sl - entry
                        break
                    if high >= tp:
                        pnl = tp - entry
                        break
                    # last fallback use close
                    if j == min(n, i+100)-1:
                        pnl = close_j - entry
                pnl_usdt = pnl * (position_usd / entry)
                balance += pnl_usdt
                trades.append(pnl_usdt)
                eq_curve.append(balance)
            elif change_pct < -5.0:
                # short
                entry = price
                tp = entry - tp_mult * atr
                sl = entry + sl_mult * atr
                pnl = 0.0
                for j in range(i+1, min(n, i+100)):
                    high = highs[j]; low = lows[j]; close_j = closes[j]
                    if high >= sl:
                        pnl = entry - sl
                        break
                    if low <= tp:
                        pnl = entry - tp
                        break
                    if j == min(n, i+100)-1:
                        pnl = entry - close_j
                pnl_usdt = pnl * (position_usd / entry)
                balance += pnl_usdt
                trades.append(pnl_usdt)
                eq_curve.append(balance)
            # else no trade

        # metrics
        trades_arr = np.array(trades) if trades else np.array([0.0])
        wins = trades_arr[trades_arr > 0]
        losses = trades_arr[trades_arr <= 0]
        win_rate = 100.0 * (len(wins) / len(trades)) if len(trades) > 0 else 0.0
        gross_profit = wins.sum() if len(wins) else 0.0
        gross_loss = abs(losses.sum()) if len(losses) else 0.0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else None
        sharpe = (trades_arr.mean() / (trades_arr.std() + 1e-9)) * (252 ** 0.5) if trades_arr.std() > 0 else None
        max_dd = 0.0
        if eq_curve:
            import numpy as _np
            ec = _np.array(eq_curve)
            peak = _np.maximum.accumulate(ec)
            dd = (ec - peak) / peak
            max_dd = float(dd.min() * 100)

        return {
            "final_balance": float(balance),
            "win_rate": float(win_rate),
            "profit_factor": pf,
            "sharpe": sharpe,
            "max_drawdown_pct": max_dd,
            "trades": len(trades)
        }
