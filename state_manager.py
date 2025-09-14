import json
import logging
from pathlib import Path
from statistics import mean

class StateManager:
    """
    bot_state.json に勝率・残高・ポジションを永続化
    """
    def __init__(self, filename="bot_state.json"):
        self.filename = Path(filename)
        self.state = {
            "balance": 10000.0,
            "positions": {},
            "trade_history": []  # {"result":"win/loss"}
        }
        self.load_state()

    def load_state(self):
        if self.filename.exists():
            try:
                with open(self.filename, "r") as f:
                    self.state = json.load(f)
                logging.info("State loaded.")
            except Exception as e:
                logging.error(f"Failed to load state: {e}")

    def save_state(self):
        try:
            with open(self.filename, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def get_balance(self):
        return self.state.get("balance", 0.0)

    def update_balance(self, new_balance: float):
        self.state["balance"] = new_balance
        self.save_state()

    def get_positions(self):
        return self.state.get("positions", {})

    def set_position(self, symbol: str, details: dict):
        self.state["positions"][symbol] = details
        self.save_state()

    def clear_position(self, symbol: str):
        if symbol in self.state["positions"]:
            del self.state["positions"][symbol]
            self.save_state()

    def record_trade_result(self, result: str):
        self.state["trade_history"].append({"result": result})
        self.save_state()

    def get_win_rate(self):
        history = self.state.get("trade_history", [])
        if not history:
            return 0.0
        wins = sum(1 for h in history if h["result"] == "win")
        return round(wins / len(history) * 100, 2)
