import json
import os
from datetime import datetime, timezone

STATE_FILE = "bot_state.json"

class StateManager:
    def __init__(self):
        self.state = {
            "balance": 10000.0,  # 初期残高
            "positions": {},
            "trade_history": []
        }
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                self.state = json.load(f)

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_balance(self):
        return self.state["balance"]

    def update_balance(self, amount):
        self.state["balance"] += amount
        self._save_state()

    def open_position(self, symbol, entry_price, size, take_profit, stop_loss):
        self.state["positions"][symbol] = {
            "entry_price": entry_price,
            "size": size,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self._save_state()

    def close_position(self, symbol, exit_price, reason="TP/SL"):
        if symbol not in self.state["positions"]:
            return None

        pos = self.state["positions"].pop(symbol)
        pnl = (exit_price - pos["entry_price"]) * pos["size"]
        pnl_pct = pnl / (pos["entry_price"] * pos["size"]) * 100

        record = {
            "symbol": symbol,
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "take_profit": pos["take_profit"],
            "stop_loss": pos["stop_loss"],
            "size": pos["size"],
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "opened_at": pos["timestamp"],
            "closed_at": datetime.now(timezone.utc).isoformat()
        }
        self.state["trade_history"].append(record)
        self.update_balance(pnl)
        self._save_state()
        return record

    def get_positions(self):
        return self.state["positions"]

    def get_trade_history(self):
        return self.state["trade_history"]
