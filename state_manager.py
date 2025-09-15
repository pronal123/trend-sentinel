# state_manager.py
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

JST = timezone(timedelta(hours=9))

class StateManager:
    """
    bot_state.json に永続化するシンプルな State Manager。
    - positions: dict[symbol] -> {entry_price, initial_amount, amount, side, tp_levels, stop_loss, opened_at}
    - trade_history: list of last N trades (each trade for partial/close)
    - balance: current USDT balance (simulated)
    - balance_history: list of {ts, balance}
    """

    def __init__(self, filename: str = "bot_state.json", max_trades: int = 1000):
        self.filename = filename
        self.lock = threading.Lock()
        self.max_trades = max_trades
        self.state = {
            "positions": {},          # symbol -> position dict
            "trade_history": [],      # list newest last
            "balance": 10000.0,       # starting simulated balance
            "balance_history": [],    # list of {"ts": iso, "balance": float}
            "summary": {},
            "last_snapshot": {}
        }
        self._load()

    def _load(self):
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                # basic validation
                if isinstance(data, dict):
                    self.state.update(data)
        except FileNotFoundError:
            self._save()
        except Exception:
            # ignore corruption; start fresh but do not crash
            self._save()

    def _save(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print("Failed to save state:", e)

    def save_state(self):
        with self.lock:
            self._save()

    # -----------------------
    # Position management
    # -----------------------
    def has_position(self, symbol: str) -> bool:
        with self.lock:
            return symbol in self.state["positions"]

    def get_positions(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.state["positions"])

    def get_position(self, symbol: str):
        with self.lock:
            return self.state["positions"].get(symbol)

    def open_position(self, symbol: str, side: str, entry_price: float, amount: float,
                      tp_levels: List[Dict[str, Any]], stop_loss: float):
        """
        Create position in state.
        tp_levels: list of {"price": float, "pct": 0.5, "closed": False}
        """
        with self.lock:
            self.state["positions"][symbol] = {
                "symbol": symbol,
                "side": side.lower(),
                "entry_price": float(entry_price),
                "initial_amount": float(amount),
                "amount": float(amount),
                "tp_levels": tp_levels,
                "stop_loss": float(stop_loss),
                "opened_at": datetime.now(JST).isoformat()
            }
            self._snapshot_balance()
            self._save()

    def reduce_position(self, symbol: str, reduce_amount: float, exit_price: float, reason: str):
        """
        Partial close: reduce reduce_amount from position.amount, record trade result for that piece.
        Returns a dict with pnl, entry_price, exit_price, amount_closed
        """
        with self.lock:
            pos = self.state["positions"].get(symbol)
            if not pos:
                return None
            # clamp
            reduce_amount = min(reduce_amount, pos["amount"])
            entry = pos["entry_price"]
            side = pos["side"]
            # approximate pnl in USDT: amount * (exit - entry) for long else (entry - exit)
            pnl_per_unit = (exit_price - entry) if side == "long" else (entry - exit_price)
            pnl = pnl_per_unit * reduce_amount
            # update amount remaining
            pos["amount"] = round(pos["amount"] - reduce_amount, 12)
            # if amount close to zero, remove position
            removed = False
            if pos["amount"] <= 1e-12:
                # final close, remove position
                del self.state["positions"][symbol]
                removed = True
            # record trade
            self._record_trade({
                "symbol": symbol,
                "side": side,
                "entry_price": entry,
                "exit_price": float(exit_price),
                "amount": float(reduce_amount),
                "pnl": float(pnl),
                "reason": reason,
                "ts": datetime.now(JST).isoformat()
            })
            # update balance
            self.state["balance"] = float(self.state.get("balance", 0.0) + pnl)
            self._snapshot_balance()
            self._save()
            return {"pnl": pnl, "entry_price": entry, "exit_price": float(exit_price), "amount": float(reduce_amount), "removed": removed}

    def close_position(self, symbol: str, exit_price: float, reason: str):
        """
        Close entire remaining position and record PnL. Uses reduce_position internally.
        """
        with self.lock:
            pos = self.state["positions"].get(symbol)
            if not pos:
                return None
            amount = float(pos["amount"])
        return self.reduce_position(symbol, amount, exit_price, reason)

    # -----------------------
    # Trade history / stats
    # -----------------------
    def _record_trade(self, trade: Dict[str, Any]):
        """
        Append trade to history and maintain max length.
        trade must have keys: symbol, side, entry_price, exit_price, amount, pnl, reason, ts
        """
        with self.lock:
            history = self.state.setdefault("trade_history", [])
            history.append(trade)
            # keep last max_trades
            if len(history) > self.max_trades:
                history = history[-self.max_trades:]
            self.state["trade_history"] = history

    def get_trade_history(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.state.get("trade_history", []))

    def get_balance(self) -> float:
        with self.lock:
            return float(self.state.get("balance", 0.0))

    def get_win_rate(self) -> float:
        with self.lock:
            hist = self.state.get("trade_history", [])
            if not hist:
                return 0.0
            wins = sum(1 for t in hist if t.get("pnl", 0) > 0)
            return wins / max(1, len(hist)) * 100.0

    def _snapshot_balance(self):
        # append to balance_history
        with self.lock:
            bh = self.state.setdefault("balance_history", [])
            bh.append({"ts": datetime.now(JST).isoformat(), "balance": float(self.state.get("balance", 0.0))})
            # keep reasonable length (e.g. last 10000)
            if len(bh) > 10000:
                bh = bh[-10000:]
            self.state["balance_history"] = bh

    # -----------------------
    # Misc
    # -----------------------
    def update_summary(self, summary: Dict[str, Any]):
        with self.lock:
            self.state["summary"] = summary
            self._save()

    def update_last_snapshot(self, snapshot: Dict[str, Any]):
        with self.lock:
            self.state["last_snapshot"] = snapshot
            self._save()

    def get_state_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "positions": dict(self.state.get("positions", {})),
                "trade_history": list(self.state.get("trade_history", [])),
                "balance": float(self.state.get("balance", 0.0)),
                "balance_history": list(self.state.get("balance_history", [])),
                "win_rate": float(self.get_win_rate()),
                "summary": dict(self.state.get("summary", {})),
                "last_snapshot": dict(self.state.get("last_snapshot", {}))
            }
