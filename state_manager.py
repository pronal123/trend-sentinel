import json
import os
import datetime
import numpy as np

class StateManager:
    def __init__(self, state_file="bot_state.json"):
        self.state_file = state_file
        self.state = {
            "balance": 10000.0,  # 初期残高 USDT
            "positions": {},
            "win_history": [],
            "trade_history": [],
            "equity_curve": [],
        }
        self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except Exception:
                pass

    def save_state(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_balance(self):
        return self.state.get("balance", 0.0)

    def update_balance(self, delta):
        self.state["balance"] += delta
        self.state["equity_curve"].append(self.state["balance"])
        self.save_state()

    def open_position(self, symbol, side, size, price, market_type="spot"):
        self.state["positions"][symbol] = {
            "side": side,
            "size": size,
            "entry_price": price,
            "market_type": market_type,
            "timestamp": datetime.datetime.now().isoformat()
        }
        self.save_state()

    def close_position(self, symbol, exit_price, pnl, win):
        if symbol in self.state["positions"]:
            del self.state["positions"][symbol]

        self.update_balance(pnl)
        self.record_trade_result(win, pnl)

    def record_trade_result(self, win, pnl):
        self.state["win_history"].append(1 if win else 0)
        self.state["trade_history"].append(pnl)
        self.save_state()

    def get_win_rate(self):
        if not self.state["win_history"]:
            return 0.0
        return sum(self.state["win_history"]) / len(self.state["win_history"]) * 100

    def get_equity_curve(self):
        return self.state.get("equity_curve", [])

    def compute_metrics(self):
        trades = self.state["trade_history"]
        if not trades:
            return {
                "pnl": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0,
                "profit_factor": 0
            }

        pnl = sum(trades)
        equity = np.cumsum(trades)
        dd = equity - np.maximum.accumulate(equity)
        max_dd = dd.min() if len(dd) else 0

        returns = np.array(trades)
        sharpe = (returns.mean() / (returns.std() + 1e-6)) * np.sqrt(252) if len(returns) > 1 else 0

        gains = sum([t for t in trades if t > 0])
        losses = abs(sum([t for t in trades if t < 0]))
        pf = (gains / losses) if losses > 0 else float("inf")

        return {
            "pnl": pnl,
            "max_drawdown": float(max_dd),
            "sharpe_ratio": float(sharpe),
            "profit_factor": float(pf)
        }
