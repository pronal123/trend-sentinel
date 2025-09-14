import json
import os
import logging
from datetime import datetime

class StateManager:
    def __init__(self, state_file="state.json", trade_history_file="trade_history.json"):
        self.state_file = state_file
        self.trade_history_file = trade_history_file
        self.state = {
            "positions": []
        }
        self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"stateロード失敗: {e}")

    def save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"state保存失敗: {e}")

    def add_position(self, symbol, side, entry_price, size, tp, sl):
        pos = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "size": size,
            "tp": tp,
            "sl": sl,
            "opened_at": datetime.utcnow().isoformat()
        }
        self.state["positions"].append(pos)
        self.save_state()

    def close_position(self, symbol, exit_price, reason="manual"):
        remaining_positions = []
        for pos in self.state["positions"]:
            if pos["symbol"] == symbol:
                pnl = (exit_price - pos["entry_price"]) * pos["size"] if pos["side"] == "long" else (pos["entry_price"] - exit_price) * pos["size"]
                self.record_trade_result({
                    "symbol": symbol,
                    "side": pos["side"],
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "size": pos["size"],
                    "pnl": pnl,
                    "reason": reason,
                    "opened_at": pos["opened_at"],
                    "closed_at": datetime.utcnow().isoformat()
                })
            else:
                remaining_positions.append(pos)
        self.state["positions"] = remaining_positions
        self.save_state()

    def record_trade_result(self, trade):
        history = []
        if os.path.exists(self.trade_history_file):
            try:
                with open(self.trade_history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                pass
        history.append(trade)
        with open(self.trade_history_file, "w") as f:
            json.dump(history[-1000:], f, indent=2)
