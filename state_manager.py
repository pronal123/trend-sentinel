import json
import os
from datetime import datetime, timezone, timedelta

STATE_FILE = "trade_state.json"
TRADE_HISTORY_FILE = "trade_history.json"

class StateManager:
    def __init__(self):
        self.state = self._load_state()
        self.trade_history = self._load_history()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        return {"positions": {}}

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def _load_history(self):
        if os.path.exists(TRADE_HISTORY_FILE):
            with open(TRADE_HISTORY_FILE, "r") as f:
                return json.load(f)
        return []

    def _save_history(self):
        with open(TRADE_HISTORY_FILE, "w") as f:
            json.dump(self.trade_history, f, indent=2)

    def open_position(self, symbol, side, size, entry_price, tp_levels, sl_level):
        self.state["positions"][symbol] = {
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "tp_levels": tp_levels,
            "sl_level": sl_level,
            "opened_at": datetime.now(timezone.utc).isoformat()
        }
        self._save_state()

    def close_position(self, symbol, close_price, reason, portion=1.0):
        pos = self.state["positions"].get(symbol)
        if not pos:
            return None

        closed_size = pos["size"] * portion
        pnl = (close_price - pos["entry_price"]) * closed_size if pos["side"] == "long" else (pos["entry_price"] - close_price) * closed_size

        trade_record = {
            "symbol": symbol,
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "close_price": close_price,
            "size": closed_size,
            "pnl": pnl,
            "reason": reason,
            "closed_at": datetime.now(timezone.utc).isoformat()
        }
        self.trade_history.append(trade_record)
        self._save_history()

        # update remaining size
        pos["size"] -= closed_size
        if pos["size"] <= 0:
            del self.state["positions"][symbol]
        self._save_state()

        return trade_record

    def get_positions(self):
        return self.state.get("positions", {})

    def get_trade_history(self, limit=1000):
        return self.trade_history[-limit:]
