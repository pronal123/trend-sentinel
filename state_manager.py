import json
import os
from datetime import datetime, timezone

STATE_FILE = "bot_state.json"
HISTORY_FILE = "trade_history.json"

class StateManager:
    def __init__(self):
        self.state = {
            "balance": float(os.getenv("START_BALANCE", "10000.0")),
            "positions": {},   # symbol -> position dict
            "win_count": 0,
            "loss_count": 0,
            "trade_count": 0,
            "balance_history": [],  # list of {"ts":iso, "balance":float}
            "last_snapshot": {}
        }
        self.trade_history = []
        self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.state.update(data)
            except Exception:
                pass
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    self.trade_history = json.load(f)
            except Exception:
                pass

    def _save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2, default=str)
        with open(HISTORY_FILE, "w") as f:
            json.dump(self.trade_history, f, indent=2, default=str)

    # ----- Position management -----
    def open_position(self, symbol: str, side: str, amount_asset: float, entry_price: float, tp_levels: list, sl_price: float):
        """Register a newly opened position (sim or after order filled)"""
        now = datetime.now(timezone.utc).isoformat()
        self.state["positions"][symbol] = {
            "symbol": symbol,
            "side": side.lower(),    # 'long' or 'short'
            "amount": float(amount_asset),
            "entry_price": float(entry_price),
            "tp_levels": [float(x) for x in tp_levels],  # e.g. [tp1, tp2, tp3]
            "sl_price": float(sl_price),
            "opened_at": now,
            "partial_steps": [0.5, 0.25, 0.25],  # default steps for partial closes
            "closed_amount": 0.0
        }
        self._save()

    def close_position(self, symbol: str, exit_price: float, reason: str, portion: float = 1.0):
        """
        Close portion (0<portion<=1) of a position and record trade.
        Returns trade record dict or None.
        """
        pos = self.state["positions"].get(symbol)
        if not pos:
            return None

        portion = float(portion)
        closed_amount = pos["amount"] * portion
        side = pos["side"]
        entry = float(pos["entry_price"])
        pnl = (exit_price - entry) * closed_amount if side == "long" else (entry - exit_price) * closed_amount

        trade = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": float(exit_price),
            "amount": closed_amount,
            "pnl": float(pnl),
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat()
        }

        # update bookkeeping
        pos["amount"] = pos["amount"] - closed_amount
        pos["closed_amount"] = pos.get("closed_amount", 0.0) + closed_amount
        if pos["amount"] <= 1e-12:
            # remove fully closed
            del self.state["positions"][symbol]

        # update balance & win/loss
        self.record_trade_result(trade)
        self.trade_history.append(trade)
        # keep only last 5000 entries to limit file size
        if len(self.trade_history) > 5000:
            self.trade_history = self.trade_history[-5000:]
        self._save()
        return trade

    # ----- Trade bookkeeping -----
    def record_trade_result(self, trade: dict):
        """Update balance and performance metrics based on trade record (expects 'pnl')."""
        pnl = float(trade.get("pnl", 0.0))
        self.state["balance"] = float(self.state.get("balance", 0.0)) + pnl
        self.state["trade_count"] = int(self.state.get("trade_count", 0)) + 1
        if pnl > 0:
            self.state["win_count"] = int(self.state.get("win_count", 0)) + 1
        else:
            self.state["loss_count"] = int(self.state.get("loss_count", 0)) + 1

        # append balance history point
        self.state.setdefault("balance_history", []).append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "balance": float(self.state["balance"])
        })

        # cap history to last 5000
        if len(self.state["balance_history"]) > 5000:
            self.state["balance_history"] = self.state["balance_history"][-5000:]

        self._save()

    # ----- Getters -----
    def has_position(self, symbol: str) -> bool:
        return symbol in self.state.get("positions", {})

    def get_positions(self):
        return self.state.get("positions", {})

    def get_balance(self) -> float:
        return float(self.state.get("balance", 0.0))

    def get_win_rate(self) -> float:
        wins = self.state.get("win_count", 0)
        trades = self.state.get("trade_count", 0)
        return (wins / trades * 100.0) if trades > 0 else 0.0

    def get_trade_history(self, limit:int=1000):
        return self.trade_history[-limit:]

    # snapshot for /status
    def update_last_snapshot(self, snapshot: dict):
        self.state["last_snapshot"] = snapshot
        self._save()

    def get_state_snapshot(self):
        snap = {
            "balance": self.get_balance(),
            "positions": self.get_positions(),
            "win_rate": self.get_win_rate(),
            "trade_count": self.state.get("trade_count", 0),
            "balance_history": self.state.get("balance_history", []),
            "last_snapshot": self.state.get("last_snapshot", {}),
        }
        return snap
