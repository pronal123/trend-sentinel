# backtester.py
import math
import statistics
from typing import List, Dict, Any, Tuple

class Backtester:
    def __init__(self, fee_pct: float = 0.0006, slippage_pct: float = 0.005):
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct

    def run_rule_backtest(self, ohlcv: List[Dict[str, Any]], rule_params: Dict[str, Any], max_trades: int = 1000) -> Dict[str, Any]:
        """
        ohlcv: list of candles dict with 'time','open','high','low','close','volume' (chronological old->new)
        Very simple rule: when 1-day change > threshold -> enter long at next open; when < -threshold -> enter short.
        TP/SL from ATR multiplier based on past ATR calculation.
        """
        trades = []
        balance = 10000.0
        for i in range(2, len(ohlcv)):
            if len(trades) >= max_trades:
                break
            today = ohlcv[i]
            prev = ohlcv[i-1]
            change_pct = (today["close"] / prev["close"] - 1.0) * 100.0
            threshold = rule_params.get("price_change_threshold_pct", 5.0)
            if change_pct >= threshold:
                # Long entry at next open (simulated as today's open)
                entry = today["open"]
                atr = self._calc_atr_from_ohlcv(ohlcv[:i+1], period=rule_params.get("atr_period", 14))
                if atr is None: continue
                tp = entry + rule_params.get("tp_atr_mult", 2.0) * atr
                sl = entry - rule_params.get("sl_atr_mult", 1.0) * atr
                # simulate exit at first candle where high >= tp or low <= sl
                pnl, exit_price = self._simulate_exit_long(ohlcv[i+1:], entry, tp, sl)
                pnl = pnl - abs(pnl) * self.fee_pct - abs(entry) * self.slippage_pct  # fees+slippage rough adjust
                trades.append({"side":"long","entry":entry,"exit":exit_price,"pnl":pnl})
                balance += pnl
            elif change_pct <= -threshold:
                entry = today["open"]
                atr = self._calc_atr_from_ohlcv(ohlcv[:i+1], period=rule_params.get("atr_period", 14))
                if atr is None: continue
                tp = entry - rule_params.get("tp_atr_mult",2.0)*atr
                sl = entry + rule_params.get("sl_atr_mult",1.0)*atr
                pnl, exit_price = self._simulate_exit_short(ohlcv[i+1:], entry, tp, sl)
                pnl = pnl - abs(pnl) * self.fee_pct - abs(entry) * self.slippage_pct
                trades.append({"side":"short","entry":entry,"exit":exit_price,"pnl":pnl})
                balance += pnl
        # compute metrics
        pnl_series = [t["pnl"] for t in trades]
        wins = sum(1 for p in pnl_series if p > 0)
        losses = sum(1 for p in pnl_series if p <= 0)
        win_rate = (wins / len(pnl_series) * 100.0) if pnl_series else 0.0
        gross_profit = sum(p for p in pnl_series if p > 0)
        gross_loss = -sum(p for p in pnl_series if p < 0)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit>0 else None
        mean = statistics.mean(pnl_series) if pnl_series else 0.0
        std = statistics.pstdev(pnl_series) if len(pnl_series) > 1 else 0.0
        sharpe = (mean / std) if std > 0 else None
        # drawdown
        equity = []
        b = 10000.0
        peak = b
        max_dd = 0.0
        for p in pnl_series:
            b += p
            equity.append(b)
            peak = max(peak, b)
            dd = (b - peak) / peak
            if dd < max_dd:
                max_dd = dd
        return {
            "n_trades": len(pnl_series),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "sharpe": sharpe,
            "max_drawdown": max_dd * 100.0,
            "final_balance": b,
            "trades": trades
        }

    def _calc_atr_from_ohlcv(self, ohlcv: List[Dict[str, Any]], period: int = 14) -> float:
        if len(ohlcv) <= period: return None
        trs = []
        for i in range(1, len(ohlcv)):
            high = ohlcv[i]["high"]
            low = ohlcv[i]["low"]
            prev_close = ohlcv[i-1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        if len(trs) < period: return None
        atr = sum(trs[-period:]) / period
        return atr

    def _simulate_exit_long(self, future_candles: List[Dict[str, Any]], entry: float, tp: float, sl: float) -> Tuple[float, float]:
        for c in future_candles:
            if c["high"] >= tp:
                return (tp - entry, tp)
            if c["low"] <= sl:
                return (sl - entry, sl)
        # if not hit, close at last close
        if future_candles:
            last = future_candles[-1]["close"]
        else:
            last = entry
        return (last - entry, last)

    def _simulate_exit_short(self, future_candles: List[Dict[str, Any]], entry: float, tp: float, sl: float) -> Tuple[float, float]:
        for c in future_candles:
            if c["low"] <= tp:
                return (entry - tp, tp)
            if c["high"] >= sl:
                return (entry - sl, sl)
        if future_candles:
            last = future_candles[-1]["close"]
        else:
            last = entry
        return (entry - last, last)
