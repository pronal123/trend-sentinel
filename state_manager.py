import json
import os
import logging
from datetime import datetime

class StateManager:
    def __init__(self, filename="bot_state.json"):
        self.filename = filename
        self.state = {
            "positions": {},
            "trade_results": {"win": 0, "loss": 0},
            "win_rate_history": []
        }
        self.load_state()

    # --- ファイルI/O ---
    def load_state(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load state: {e}")

    def save_state(self):
        try:
            with open(self.filename, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    # --- 勝率管理 ---
    def record_trade_result(self, token_id, result: str):
        """トレード結果を記録し、勝率履歴を更新する"""
        if result not in ["win", "loss"]:
            return
        self.state["trade_results"][result] += 1

        win_rate = self.get_win_rate()
        self.state["win_rate_history"].append({
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "value": win_rate
        })
        self.save_state()

    def get_win_rate(self) -> float:
        wins = self.state["trade_results"]["win"]
        losses = self.state["trade_results"]["loss"]
        total = wins + losses
        return (wins / total) * 100 if total > 0 else 0.0

    def get_win_rate_history(self):
        return {
            "timestamps": [x["time"] for x in self.state.get("win_rate_history", [])],
            "values": [x["value"] for x in self.state.get("win_rate_history", [])]
        }

    # --- ポジション管理 ---
    def set_position(self, token_id, is_active: bool, details=None):
        if is_active:
            self.state["positions"][token_id] = details or {}
        else:
            self.state["positions"].pop(token_id, None)
        self.save_state()

    def has_position(self, token_id):
        return token_id in self.state["positions"]

    def get_position_details(self, token_id):
        return self.state["positions"].get(token_id, {})

    def get_all_active_positions(self):
        return self.state["positions"]

    def record_trade_result_and_close(self, token_id, result, pnl=None):
        """トレード結果を記録しつつポジションを閉じる"""
        self.record_trade_result(token_id, result)
        self.set_position(token_id, False, None)

