# state_manager.py
import json
import os
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

LOCK = threading.Lock()

DEFAULT_STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
JST = timezone(timedelta(hours=9))

class StateManager:
    def __init__(self, filename: str = DEFAULT_STATE_FILE):
        self.filename = filename
        self.state: Dict[str, Any] = {
            "positions": {},             # symbol -> position dict
            "balance_history": [],       # list of {"timestamp": iso, "balance": float}
            "trade_history": [],         # list of trades
            "stats": {},                 # aggregated stats cache
            "last_snapshot": {},
        }
        self._load()

    def _load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.state.update(json.load(f))
            except Exception:
                # ignore corrupt file — start fresh but keep backup
                try:
                    os.rename(self.filename, self.filename + ".bak")
                except Exception:
                    pass
                self._save()

    def _save(self):
        with LOCK:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2, default=str)

    # --- Position management ---
    def open_position(self, symbol: str, side: str, entry_price: float, amount: float,
                      take_profit: float, stop_loss: float, leverage: float = 1.0):
        """
        Register an open position (simulated or after execution).
        Overwrites existing position for same symbol.
        """
        pos = {
            "symbol": symbol,
            "side": side.lower(),
            "entry_price": float(entry_price),
            "amount": float(amount),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
            "leverage": float(leverage),
            "opened_at": datetime.now(JST).isoformat(),
        }
        self.state["positions"][symbol] = pos
        self._save()
        return pos

    def has_position(self, symbol: str) -> bool:
        return symbol in self.state.get("positions", {})

    def get_positions(self) -> Dict[str, Any]:
        return self.state.get("positions", {})

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.state.get("positions", {}).get(symbol)

    def close_position(self, symbol: str, exit_price: float, reason: str = "CLOSED") -> Dict[str, Any]:
        """
        Close and record PnL. Returns the trade record.
        """
        pos = self.get_position(symbol)
        if not pos:
            raise KeyError("No position for " + symbol)
        entry = float(pos["entry_price"])
        amount = float(pos["amount"])
        side = pos["side"]
        # PnL in asset * price (USDT): for futures USDT perpetual with linear contracts, approximate:
        if side == "long":
            pnl = (float(exit_price) - entry) * amount * pos.get("leverage", 1.0)
        else:
            pnl = (entry - float(exit_price)) * amount * pos.get("leverage", 1.0)
        trade = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": float(exit_price),
            "amount": amount,
            "pnl": float(pnl),
            "opened_at": pos.get("opened_at"),
            "closed_at": datetime.now(JST).isoformat(),
            "reason": reason
        }
        # store trade
        self.state.setdefault("trade_history", []).append(trade)
        # keep only last 2000 for safety
        if len(self.state["trade_history"]) > 5000:
            self.state["trade_history"] = self.state["trade_history"][-5000:]
        # remove position
        del self.state["positions"][symbol]
        # update balance history: add pnl to last balance
        last_balance = self.get_balance()
        new_balance = last_balance + pnl
        self.append_balance(new_balance)
        # update stats
        self._recalculate_stats()
        self._save()
        return trade

    # --- Balance / history ---
    def append_balance(self, balance: float):
        self.state.setdefault("balance_history", []).append({
            "timestamp": datetime.now(JST).isoformat(),
            "balance": float(balance)
        })
        # cap history
        if len(self.state["balance_history"]) > 10000:
            self.state["balance_history"] = self.state["balance_history"][-10000:]
        self._save()

    def get_balance(self) -> float:
        hist = self.state.get("balance_history", [])
        if not hist:
            # default starting balance
            return float(os.getenv("STARTING_BALANCE", "10000"))
        return float(hist[-1]["balance"])

    # --- Trade history and stats ---
    def record_trade_result(self, trade: Dict[str, Any]):
        """
        Append trade object (must include 'pnl' and 'side' etc).
        Useful when trades are executed outside close_position.
        """
        self.state.setdefault("trade_history", []).append(trade)
        if len(self.state["trade_history"]) > 5000:
            self.state["trade_history"] = self.state["trade_history"][-5000:]
        # update balance
        last_balance = self.get_balance()
        new_balance = last_balance + float(trade.get("pnl", 0.0))
        self.append_balance(new_balance)
        self._recalculate_stats()
        self._save()

    def _recalculate_stats(self):
        trades = self.state.get("trade_history", [])[-1000:]
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]
        win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit>0 else 0.0
        # compute returns series for sharpe
        import numpy as np
        returns = np.array([t["pnl"] for t in trades])
        sharpe = (returns.mean() / (returns.std() + 1e-9) * (252 ** 0.5)) if returns.size > 1 and returns.std()>0 else 0.0
        # drawdown on balance history
        balances = [b["balance"] for b in self.state.get("balance_history", [])]
        max_dd = 0.0
        if balances:
            import numpy as _np
            arr = _np.array(balances)
            peak = _np.maximum.accumulate(arr)
            dd = (arr - peak) / peak
            max_dd = float(dd.min() * 100)
        self.state["stats"] = {
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "sharpe": float(sharpe),
            "max_drawdown_pct": float(max_dd),
            "total_trades": len(trades)
        }

    def get_stats(self) -> Dict[str, Any]:
        # ensure recalculated
        self._recalculate_stats()
        return self.state.get("stats", {})

    # --- snapshot / status helpers ---
    def update_last_snapshot(self, snap: Dict[str, Any]):
        self.state["last_snapshot"] = snap
        self._save()

    def get_state_snapshot(self) -> Dict[str, Any]:
        return {
            "positions": self.get_positions(),
            "balance_history": self.state.get("balance_history", []),
            "trade_history": self.state.get("trade_history", [])[-1000:],
            "stats": self.get_stats(),
            "last_snapshot": self.state.get("last_snapshot", {})
        }

    # --- persistence control ---
    def save_state(self):
        self._save()

    def load_state(self):
        self._load()
