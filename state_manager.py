import json
import os
from datetime import datetime
import pytz
import logging


class StateManager:
    def __init__(self, state_file="bot_state.json"):
        self.state_file = state_file
        self.state = {
            "balance": 10000.0,   # 初期残高（仮想USD）
            "positions": {},      # { "BTCUSDT": {"side": "LONG", "amount": 0.1, "entry": 27000} }
            "trades": [],         # 取引履歴
            "win_rate_history": [],  # 勝率履歴 [{time, win_rate}]
            "snapshots": []       # 市場スナップショット履歴
        }
        self._load()

    # ==============================
    # 永続化
    # ==============================
    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load state file: {e}")

    def _save(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save state file: {e}")

    # ==============================
    # 残高管理
    # ==============================
    def update_balance(self, amount: float):
        self.state["balance"] += amount
        self._save()

    def get_balance(self) -> float:
        return self.state.get("balance", 0.0)

    # ==============================
    # 勝率管理
    # ==============================
    def record_trade_result(self, win: bool):
        """取引の勝敗を記録し、勝率履歴を更新"""
        self.state["trades"].append({
            "time": datetime.now(pytz.timezone("Asia/Tokyo")).isoformat(),
            "result": "WIN" if win else "LOSS"
        })

        # 勝率計算
        wins = sum(1 for t in self.state["trades"] if t["result"] == "WIN")
        total = len(self.state["trades"])
        win_rate = (wins / total * 100) if total > 0 else 0

        self.state["win_rate_history"].append({
            "time": datetime.now(pytz.timezone("Asia/Tokyo")).isoformat(),
            "win_rate": win_rate
        })
        self._save()

    def get_win_rate(self) -> float:
        if not self.state["trades"]:
            return 0.0
        wins = sum(1 for t in self.state["trades"] if t["result"] == "WIN")
        total = len(self.state["trades"])
        return (wins / total * 100)

    def get_win_rate_history(self):
        return self.state.get("win_rate_history", [])

    # ==============================
    # ポジション管理
    # ==============================
    def open_position(self, symbol: str, side: str, amount: float, entry: float):
        self.state["positions"][symbol] = {
            "side": side,
            "amount": amount,
            "entry": entry,
            "opened_at": datetime.now(pytz.timezone("Asia/Tokyo")).isoformat()
        }
        self._save()

    def close_position(self, symbol: str, exit_price: float):
        pos = self.state["positions"].pop(symbol, None)
        if pos:
            pnl = (exit_price - pos["entry"]) * pos["amount"]
            if pos["side"] == "SHORT":
                pnl = -pnl
            self.update_balance(pnl)
            self.record_trade_result(win=(pnl > 0))
        self._save()

    def get_positions(self):
        return self.state.get("positions", {})

    # ==============================
    # スナップショット保存
    # ==============================
    def save_snapshot(self, snapshot: dict):
        self.state["snapshots"].append({
            "time": datetime.now(pytz.timezone("Asia/Tokyo")).isoformat(),
            "data": snapshot
        })
        # 古いデータを整理（例: 100件以上なら削除）
        if len(self.state["snapshots"]) > 100:
            self.state["snapshots"] = self.state["snapshots"][-100:]
        self._save()

    def get_latest_snapshot(self):
        if not self.state["snapshots"]:
            return {}
        return self.state["snapshots"][-1]
