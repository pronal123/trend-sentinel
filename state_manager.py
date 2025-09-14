# state_manager.py
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

JST = timezone(timedelta(hours=9))
STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
MAX_HISTORY = 1000

class StateManager:
    def __init__(self):
        self.state = {
            "balance": float(os.getenv("INITIAL_BALANCE", 10000.0)),
            "positions": {},   # symbol -> {side, entry_price, amount, tp, sl, opened_at}
            "trade_history": [],  # list of trade records
            "balance_history": [], # list of {"timestamp","balance"}
            "last_snapshot": {}
        }
        self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error("Failed to load state file: %s", e)

    def _save(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error("Failed to save state file: %s", e)

    # --- balance & snapshot ---
    def get_balance(self) -> float:
        return float(self.state.get("balance", 0.0))

    def set_balance(self, balance: float):
        self.state["balance"] = float(balance)
        self._save()

    def snapshot_balance(self):
        ts = datetime.now(JST).isoformat()
        self.state.setdefault("balance_history", []).append({"timestamp": ts, "balance": self.get_balance()})
        # keep limited size
        if len(self.state["balance_history"]) > 5000:
            self.state["balance_history"] = self.state["balance_history"][-5000:]
        self._save()

    # --- positions ---
    def has_position(self, symbol: str) -> bool:
        return symbol in self.state.get("positions", {})

    def open_position(self, symbol: str, side: str, entry_price: float, amount: float, take_profit: float, stop_loss: float):
        """Open simulated position and persist. amount = asset units (not USD)."""
        opened_at = datetime.now(JST).isoformat()
        self.state.setdefault("positions", {})[symbol] = {
            "side": side,
            "entry_price": float(entry_price),
            "amount": float(amount),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
            "opened_at": opened_at
        }
        # snapshot balance
        self.snapshot_balance()
        self._save()
        return self.state["positions"][symbol]

    def close_position(self, symbol: str, exit_price: float, reason: str = "TP/SL"):
        """Close position, compute pnl (USDT), record trade_history and update balance."""
        positions = self.state.get("positions", {})
        if symbol not in positions:
            return None
        pos = positions.pop(symbol)
        side = pos["side"]
        entry = float(pos["entry_price"])
        amount = float(pos["amount"])  # asset qty
        # PnL calculation: for long: (exit-entry)*amount ; for short: (entry-exit)*amount
        pnl = (exit_price - entry) * amount if side.lower() == "long" else (entry - exit_price) * amount
        # update balance
        self.state["balance"] = float(self.state.get("balance", 0.0)) + float(pnl)
        record = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": float(exit_price),
            "amount": amount,
            "take_profit": pos.get("take_profit"),
            "stop_loss": pos.get("stop_loss"),
            "pnl": float(pnl),
            "reason": reason,
            "opened_at": pos.get("opened_at"),
            "closed_at": datetime.now(JST).isoformat()
        }
        self.state.setdefault("trade_history", []).append(record)
        # trim history to MAX_HISTORY
        if len(self.state["trade_history"]) > MAX_HISTORY:
            self.state["trade_history"] = self.state["trade_history"][-MAX_HISTORY:]
        self.snapshot_balance()
        self._save()
        return record

    def record_trade_result(self, record: dict):
        """Externally called to append trade records (e.g. from actual executor)."""
        self.state.setdefault("trade_history", []).append(record)
        if len(self.state["trade_history"]) > MAX_HISTORY:
            self.state["trade_history"] = self.state["trade_history"][-MAX_HISTORY:]
        # update balance if pnl provided
        pnl = record.get("pnl")
        if pnl is not None:
            self.state["balance"] = float(self.state.get("balance", 0.0)) + float(pnl)
        self.snapshot_balance()
        self._save()

    def get_positions(self):
        return self.state.get("positions", {})

    def get_trade_history(self, limit=1000):
        return self.state.get("trade_history", [])[-min(limit, MAX_HISTORY):]

    def get_balance_history(self):
        return self.state.get("balance_history", [])

    def get_win_rate(self):
        history = self.state.get("trade_history", [])
        if not history:
            return 0.0
        wins = sum(1 for t in history if t.get("pnl", 0) > 0)
        return float(wins) / len(history) * 100.0

    def update_last_snapshot(self, snapshot: dict):
        self.state["last_snapshot"] = snapshot
        self._save()

    def get_state_snapshot(self):
        return {
            "balance": self.get_balance(),
            "positions": self.get_positions(),
            "trade_history": self.get_trade_history(),
            "balance_history": self.get_balance_history(),
            "win_rate": self.get_win_rate(),
            "last_snapshot": self.state.get("last_snapshot", {})
        }
