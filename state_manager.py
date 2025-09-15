# state_manager.py
import json
import os
import threading
import time
from typing import Dict, Any, Optional, List

STATE_FILE = os.getenv("BOT_STATE_FILE", "bot_state.json")
MAX_HISTORY = int(os.getenv("BACKTEST_TRADES", "1000"))

class StateManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = {
            "balance": 10000.0,
            "positions": {},  # symbol -> details
            "trade_history": [],  # list of trades (most recent last)
            "balance_history": [],  # snapshots {ts, balance}
            "stats": {  # live stats
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "profit_factor": None,
                "sharpe": None,
                "max_drawdown": None
            },
            "last_snapshot": {},
            "summary": {},
        }
        self._load_state()

    # ---------- Persistence ----------
    def _load_state(self):
        with self.lock:
            if os.path.exists(STATE_FILE):
                try:
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    # Basic merge to ensure keys exist
                    self.state.update(loaded)
                except Exception:
                    # If file corrupted, ignore and start fresh
                    self._save_state()
            else:
                self._save_state()

    def _save_state(self):
        with self.lock:
            try:
                tmp = STATE_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, ensure_ascii=False, indent=2, default=str)
                os.replace(tmp, STATE_FILE)
            except Exception as e:
                print("State save failed:", e)

    def save_state(self):
        self._save_state()

    # ---------- Position management ----------
    def has_position(self, symbol: str) -> bool:
        with self.lock:
            return symbol in self.state["positions"]

    def get_positions(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.state["positions"])

    def open_position(self, symbol: str, side: str, entry_price: float, amount_asset: float,
                      take_profit: float, stop_loss: float, leverage: float = 1.0):
        """
        Register position in memory (paper trade or after real order).
        """
        with self.lock:
            pos = {
                "symbol": symbol,
                "side": side.lower(),
                "entry_price": float(entry_price),
                "amount": float(amount_asset),
                "take_profit": float(take_profit),
                "stop_loss": float(stop_loss),
                "leverage": float(leverage),
                "opened_at": time.time()
            }
            self.state["positions"][symbol] = pos
            self._append_balance_history(self.state.get("balance", 0.0))
            self._save_state()

    def close_position(self, symbol: str, exit_price: float, reason: str = "MANUAL") -> Dict[str, Any]:
        """
        Close and record trade result. Returns dict with computed pnl etc.
        """
        with self.lock:
            if symbol not in self.state["positions"]:
                raise KeyError("No position for symbol: " + symbol)
            pos = self.state["positions"].pop(symbol)
            # compute PnL in USDT assuming futures USDT perpetual, amount is asset units
            side = pos["side"]
            amt = float(pos["amount"])
            entry = float(pos["entry_price"])
            exit_p = float(exit_price)
            # For futures USDT perpetual linear contracts, PnL = (exit - entry) * amount for long,
            # and (entry - exit) * amount for short.
            if side == "long":
                pnl = (exit_p - entry) * amt * float(pos.get("leverage", 1.0))
            else:
                pnl = (entry - exit_p) * amt * float(pos.get("leverage", 1.0))

            # Update balance
            self.state["balance"] = float(self.state.get("balance", 10000.0)) + pnl
            self._append_balance_history(self.state["balance"])

            trade = {
                "timestamp": time.time(),
                "symbol": symbol,
                "side": side,
                "entry_price": entry,
                "exit_price": exit_p,
                "amount": amt,
                "pnl": pnl,
                "reason": reason
            }
            self._append_trade_history(trade)
            # Update performance stats
            result = "win" if pnl > 0 else "loss"
            self.record_trade_result(result, pnl=pnl)
            self._save_state()

            return {
                "entry_price": entry,
                "exit_price": exit_p,
                "pnl": pnl,
                "reason": reason
            }

    # ---------- Trade history ----------
    def _append_trade_history(self, trade: Dict[str, Any]):
        with self.lock:
            self.state["trade_history"].append(trade)
            # limit to MAX_HISTORY
            if len(self.state["trade_history"]) > MAX_HISTORY:
                # keep only most recent MAX_HISTORY
                self.state["trade_history"] = self.state["trade_history"][-MAX_HISTORY:]

    def record_trade_result(self, result: str, pnl: float = 0.0, **kwargs):
        """
        Update stats when a trade is recorded.
        result: 'win' or 'loss'
        """
        with self.lock:
            st = self.state["stats"]
            if result == "win":
                st["wins"] = st.get("wins", 0) + 1
            else:
                st["losses"] = st.get("losses", 0) + 1

            # recompute win_rate
            total = st.get("wins", 0) + st.get("losses", 0)
            st["win_rate"] = (st.get("wins", 0) / total) * 100.0 if total > 0 else 0.0

            # accumulate P&L list for more metrics
            if "pnl_history" not in st:
                st["pnl_history"] = []
            st["pnl_history"].append(float(pnl))
            if len(st["pnl_history"]) > MAX_HISTORY:
                st["pnl_history"] = st["pnl_history"][-MAX_HISTORY:]

            # recompute profit factor and sharpe and max drawdown
            profits = [x for x in st["pnl_history"] if x > 0]
            losses = [-x for x in st["pnl_history"] if x < 0]
            gross_profit = sum(profits)
            gross_loss = sum(losses)
            st["profit_factor"] = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else None)

            # Sharpe (annualized) based on pnl series (approx)
            import math
            import statistics
            if len(st["pnl_history"]) >= 2:
                mean = statistics.mean(st["pnl_history"])
                std = statistics.pstdev(st["pnl_history"])
                # approximate sharpe with sqrt(252*... ) but since trades aren't daily, keep raw normalized:
                st["sharpe"] = (mean / std) if std > 0 else None
            else:
                st["sharpe"] = None

            # max drawdown from balance_history if exists
            if self.state.get("balance_history"):
                balances = [b.get("balance", 0.0) for b in self.state["balance_history"]]
                peak = balances[0]
                max_dd = 0.0
                for b in balances:
                    peak = max(peak, b)
                    dd = (b - peak) / peak
                    if dd < max_dd:
                        max_dd = dd
                st["max_drawdown"] = max_dd * 100.0
            else:
                st["max_drawdown"] = None

            self._save_state()

    # ---------- Balance history ----------
    def _append_balance_history(self, balance: float):
        with self.lock:
            self.state.setdefault("balance_history", []).append({"timestamp": time.time(), "balance": float(balance)})
            # limit to MAX_HISTORY * 3 maybe
            if len(self.state["balance_history"]) > MAX_HISTORY * 3:
                self.state["balance_history"] = self.state["balance_history"][-(MAX_HISTORY * 3):]

    # ---------- Snapshot / Stats Access ----------
    def update_last_snapshot(self, snapshot: Dict[str, Any]):
        with self.lock:
            self.state["last_snapshot"] = snapshot
            self._save_state()

    def get_state_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            # return safe shallow copy
            return {
                "balance": float(self.state.get("balance", 0.0)),
                "positions": dict(self.state.get("positions", {})),
                "trade_history": list(self.state.get("trade_history", [])),
                "balance_history": list(self.state.get("balance_history", [])),
                "stats": dict(self.state.get("stats", {})),
                "last_snapshot": dict(self.state.get("last_snapshot", {})),
                "summary": dict(self.state.get("summary", {}))
            }

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.state.get("stats", {}))

    def get_win_rate(self) -> float:
        with self.lock:
            st = self.state.get("stats", {})
            return float(st.get("win_rate", 0.0))

    # utility
    def get_balance(self) -> float:
        with self.lock:
            return float(self.state.get("balance", 0.0))
