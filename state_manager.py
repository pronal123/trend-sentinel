import logging
import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime


class StateManager:
    """
    トレード状態・ポジション・残高を管理するクラス。
    部分利確・トレーリング・勝率統計をサポート。
    """

    def __init__(self, starting_balance: float = 1000.0):
        self.balance = starting_balance
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.realized_pnl = 0.0

    # ========== balance ==========
    def get_balance(self) -> float:
        return self.balance

    def update_balance(self, delta: float):
        self.balance += delta
        logging.info(f"Balance updated: {self.balance:.2f} USDT")

    # ========== positions ==========
    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_position(self, symbol: str, side: str, entry_price: float,
                      amount: float, tp: float, sl: float, leverage: float):
        self.positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "amount": amount,
            "take_profit": tp,
            "stop_loss": sl,
            "leverage": leverage,
            "opened_at": datetime.utcnow().isoformat(),
        }
        logging.info(f"OPEN {side} {symbol} entry={entry_price:.4f} tp={tp:.4f} sl={sl:.4f}")

    def close_position(self, symbol: str, exit_price: float,
                       reason: str = "", portion: float = 1.0) -> Dict[str, Any]:
        if symbol not in self.positions:
            raise KeyError(f"No open position for {symbol}")
        pos = self.positions[symbol]

        side = pos["side"]
        amount = pos["amount"] * portion
        entry = pos["entry_price"]

        pnl = (exit_price - entry) * amount if side == "long" else (entry - exit_price) * amount
        self.realized_pnl += pnl
        self.update_balance(pnl)

        trade_record = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": exit_price,
            "amount": amount,
            "pnl": pnl,
            "reason": reason,
            "closed_at": datetime.utcnow().isoformat(),
        }
        self.trade_history.append(trade_record)

        if portion >= 1.0:
            del self.positions[symbol]
        else:
            self.positions[symbol]["amount"] -= amount

        logging.info(f"CLOSE {portion*100:.0f}% {symbol} at {exit_price:.4f}, pnl={pnl:.2f}")
        return trade_record

    def trail_stop(self, symbol: str, current_price: float, trail_pct: float = 0.01):
        """価格が有利方向に進んだ場合、SLを更新"""
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        if pos["side"] == "long":
            new_sl = max(pos["stop_loss"], current_price * (1 - trail_pct))
            if new_sl > pos["stop_loss"]:
                pos["stop_loss"] = new_sl
        else:
            new_sl = min(pos["stop_loss"], current_price * (1 + trail_pct))
            if new_sl < pos["stop_loss"]:
                pos["stop_loss"] = new_sl

    # ========== stats ==========
    def get_win_rate(self) -> float:
        if not self.trade_history:
            return 0.0
        wins = sum(1 for t in self.trade_history if t["pnl"] > 0)
        return wins / len(self.trade_history)

    def get_risk_reward(self) -> float:
        losses = [t["pnl"] for t in self.trade_history if t["pnl"] < 0]
        wins = [t["pnl"] for t in self.trade_history if t["pnl"] > 0]
        if not wins or not losses:
            return 0.0
        return abs(statistics.mean(wins) / statistics.mean(losses))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "balance": self.balance,
            "realized_pnl": self.realized_pnl,
            "open_positions": list(self.positions.keys()),
            "win_rate": self.get_win_rate(),
            "rr_ratio": self.get_risk_reward(),
            "trades": len(self.trade_history),
        }
