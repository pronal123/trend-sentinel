# state_manager.py
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

STATE_FILE = os.getenv("BOT_STATE_FILE", "bot_state.json")


class StateManager:
    def __init__(self, filename: str = STATE_FILE):
        self.filename = filename
        self.state: Dict[str, Any] = {
            "balance": float(os.getenv("INITIAL_BALANCE", "10000")),
            "positions": {},  # symbol -> position dict
            "trade_history": [],  # list of trades (dict)
            "last_snapshot": {},
        }
        self._load()

    def _load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception:
                # corrupt or incompatible -> keep default
                pass

    def _save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2, default=str)

    # --- balance ---
    def get_balance(self) -> float:
        return float(self.state.get("balance", 0.0))

    def set_balance(self, value: float):
        self.state["balance"] = float(value)
        self._save()

    # --- positions management ---
    def open_position(self, symbol: str, side: str, size_asset: float, entry_price: float, take_profit: float, stop_loss: float, meta: Optional[Dict] = None):
        self.state["positions"][symbol] = {
            "symbol": symbol,
            "side": side.lower(),
            "size_asset": float(size_asset),
            "entry_price": float(entry_price),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
            "meta": meta or {},
            "opened_at": datetime.utcnow().isoformat()
        }
        self._save()

    def has_position(self, symbol: str) -> bool:
        return symbol in self.state.get("positions", {})

    def get_positions(self) -> Dict[str, Any]:
        return self.state.get("positions", {})

    def get_position(self, symbol: str) -> Optional[Dict]:
        return self.state.get("positions", {}).get(symbol)

    def close_position(self, symbol: str, exit_price: float, reason: str = "manual") -> Optional[Dict]:
        pos = self.get_position(symbol)
        if not pos:
            return None
        side = pos["side"]
        size = float(pos["size_asset"])
        entry = float(pos["entry_price"])
        # PnL in asset * price = USDT
        pnl_asset = (exit_price - entry) * size if side == "long" else (entry - exit_price) * size
        pnl_usdt = float(pnl_asset)
        trade_record = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": float(exit_price),
            "size_asset": size,
            "pnl": pnl_usdt,
            "tp": pos["take_profit"],
            "sl": pos["stop_loss"],
            "reason": reason,
            "opened_at": pos.get("opened_at"),
            "closed_at": datetime.utcnow().isoformat()
        }
        # append history and remove position
        self.state.setdefault("trade_history", []).append(trade_record)
        # maintain only last 5000 for safety
        self.state["trade_history"] = self.state["trade_history"][-5000:]
        # update balance
        self.state["balance"] = float(self.get_balance() + pnl_usdt)
        # remove position
        del self.state["positions"][symbol]
        self._save()
        return trade_record

    def get_trade_history(self, last_n: int = 1000) -> List[Dict]:
        return list(self.state.get("trade_history", []))[-last_n:]

    # statistics
    def get_stats(self, last_n: int = 1000) -> Dict:
        trades = self.get_trade_history(last_n)
        if not trades:
            return {"trades": 0, "win_rate": 0.0, "profit": 0.0, "profit_factor": None}
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(wins) / len(trades) * 100.0
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses)) or 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
        total = sum(t["pnl"] for t in trades)
        return {
            "trades": len(trades),
            "win_rate": win_rate,
            "profit": total,
            "profit_factor": profit_factor,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss
        }

    def update_last_snapshot(self, snapshot: Dict):
        self.state["last_snapshot"] = snapshot
        self._save()

    def get_state_snapshot(self) -> Dict:
        snap = {
            "balance": self.get_balance(),
            "positions": self.get_positions(),
            "trade_history_count": len(self.state.get("trade_history", [])),
            "last_snapshot": self.state.get("last_snapshot", {}),
            "stats": self.get_stats()
        }
        return snap
