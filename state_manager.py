import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List


class StateManager:
    """
    Handles persistent state of the bot:
      - Last snapshot (market info per cycle)
      - Active positions with TP/SL, partial TP, trailing
      - Account balance (simulation mode)
    """

    def __init__(self, filepath: str = "state.json", initial_balance: float = 10000.0):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.state: Dict[str, Any] = {
            "last_snapshot": None,
            "positions": {},   # {symbol: {...}}
            "balance": initial_balance,
            "last_update": None,
        }
        self._load_state()

    # ---------------- Internal persistence ----------------
    def _load_state(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load state file: {e}")
        else:
            self._save_state()

    def _save_state(self):
        try:
            with self.lock:
                with open(self.filepath, "w") as f:
                    json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Failed to save state file: {e}")

    # ---------------- Snapshot management ----------------
    def get_last_snapshot(self) -> Any:
        return self.state.get("last_snapshot")

    def update_last_snapshot(self, snapshot: Any):
        with self.lock:
            self.state["last_snapshot"] = snapshot
            self.state["last_update"] = datetime.utcnow().isoformat()
            self._save_state()

    # ---------------- Position management ----------------
    def get_positions(self) -> Dict[str, Any]:
        return self.state.get("positions", {})

    def has_position(self, symbol: str) -> bool:
        return symbol in self.state.get("positions", {})

    def add_position(self, symbol: str, position: Dict[str, Any]):
        """Add or update a position with full structure."""
        default_position = {
            "symbol": symbol,
            "side": position.get("side", "long"),
            "entry": position.get("entry"),
            "size": position.get("size", 0.0),
            "tp": position.get("tp"),
            "sl": position.get("sl"),
            "trail_active": position.get("trail_active", False),
            "trail_offset": position.get("trail_offset", None),
            "partial_targets": position.get("partial_targets", []),  # list of dicts
            "status": "open",
            "opened_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        with self.lock:
            self.state["positions"][symbol] = default_position
            self.state["last_update"] = datetime.utcnow().isoformat()
            self._save_state()

    def update_position(self, symbol: str, updates: Dict[str, Any]):
        with self.lock:
            if symbol in self.state["positions"]:
                self.state["positions"][symbol].update(updates)
                self.state["positions"][symbol]["updated_at"] = datetime.utcnow().isoformat()
                self.state["last_update"] = datetime.utcnow().isoformat()
                self._save_state()

    def remove_position(self, symbol: str):
        with self.lock:
            if symbol in self.state["positions"]:
                del self.state["positions"][symbol]
                self.state["last_update"] = datetime.utcnow().isoformat()
                self._save_state()

    # ---------------- Balance management ----------------
    def get_balance(self) -> float:
        return float(self.state.get("balance", 0.0))

    def adjust_balance(self, delta: float):
        with self.lock:
            self.state["balance"] = float(self.state.get("balance", 0.0)) + delta
            self.state["last_update"] = datetime.utcnow().isoformat()
            self._save_state()

    # ---------------- Advanced Position Logic ----------------
    def check_partial_take_profits(self, symbol: str, price: float):
        """Check if partial TP triggers at current price."""
        if symbol not in self.state["positions"]:
            return []

        pos = self.state["positions"][symbol]
        executed_targets = []
        side = pos["side"]

        for target in pos.get("partial_targets", []):
            if target["executed"]:
                continue

            trigger = (
                price >= target["price"] if side == "long" else price <= target["price"]
            )
            if trigger:
                portion = pos["size"] * target["size_pct"]
                pnl = (price - pos["entry"]) * portion if side == "long" else (pos["entry"] - price) * portion
                self.adjust_balance(pnl)
                target["executed"] = True
                executed_targets.append(target)
                print(f"✅ Partial TP executed: {symbol} @ {price}, PnL={pnl:.2f}")

        self.update_position(symbol, {"partial_targets": pos["partial_targets"]})
        return executed_targets

    def update_trailing_stop(self, symbol: str, price: float):
        """Update SL if trailing is active and price moves in favor."""
        if symbol not in self.state["positions"]:
            return None

        pos = self.state["positions"][symbol]
        if not pos.get("trail_active") or not pos.get("trail_offset"):
            return None

        side = pos["side"]
        trail_offset = pos["trail_offset"]
        new_sl = None

        if side == "long":
            candidate_sl = price - trail_offset
            if pos["sl"] is None or candidate_sl > pos["sl"]:
                new_sl = candidate_sl
        else:  # short
            candidate_sl = price + trail_offset
            if pos["sl"] is None or candidate_sl < pos["sl"]:
                new_sl = candidate_sl

        if new_sl:
            self.update_position(symbol, {"sl": new_sl})
            print(f"🔄 Trailing SL updated: {symbol} → {new_sl}")
            return new_sl
        return None

    def realize_pnl(self, symbol: str, close_price: float):
        """Close position fully and realize PnL."""
        if symbol not in self.state["positions"]:
            return 0.0

        pos = self.state["positions"][symbol]
        side = pos["side"]
        size = pos["size"]
        entry = pos["entry"]

        pnl = (close_price - entry) * size if side == "long" else (entry - close_price) * size
        self.adjust_balance(pnl)

        self.remove_position(symbol)
        print(f"💰 Position closed: {symbol}, PnL={pnl:.2f}")
        return pnl

    # ---------------- Utility ----------------
    def get_state_snapshot(self) -> Dict[str, Any]:
        return self.state
