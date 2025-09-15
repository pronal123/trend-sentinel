# state_manager.py
import time
import json
import os
import logging

class StateManager:
    def __init__(self, state_file="state.json", notification_interval=21600):  # 6 hours
        self.state_file = state_file
        self.notification_interval = notification_interval

        # デフォルト状態
        self.state = {
            "notified_tokens": {},
            "positions": {},  # {'token_id': {'in_position': True, 'details': {...}}}
            "trade_history": [],  # [{'token_id': str, 'result': 'win'/'loss'}]
            "pending_signals": {},  # {'token_id': {'score': 85, 'entry_price': 50000, ...}}
            "daily_pnl": {},  # {'YYYY-MM-DD': {'realized_usdt': float, 'realized_jpy': float, 'entry_count': int, 'exit_count': int}}
            "last_snapshot": None,  # 直近のスナップショット
        }

        self._load_state()

    # =====================
    # 状態保存 / 読み込み
    # =====================
    def _save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state.update(json.load(f))
            except Exception as e:
                logging.error(f"Failed to load state: {e}")

    # =====================
    # シグナル管理
    # =====================
    def add_pending_signal(self, token_id, details):
        self.state["pending_signals"][token_id] = details
        logging.info(f"Signal for {token_id} is now PENDING CONFIRMATION.")
        self._save_state()

    def get_and_clear_pending_signals(self):
        pending = self.state["pending_signals"]
        self.state["pending_signals"] = {}
        self._save_state()
        return pending

    # =====================
    # ポジション管理
    # =====================
    def has_position(self, token_id):
        return self.state["positions"].get(token_id, {}).get("in_position", False)

    def set_position(self, token_id, status, details=None):
        self.state["positions"][token_id] = {"in_position": status, "details": details}
        logging.info(f"Position for {token_id} set to {status}.")
        self._save_state()

    def get_position_details(self, token_id):
        return self.state["positions"].get(token_id, {}).get("details")

    def get_all_positions(self):
        return {t: pos["details"] for t, pos in self.state["positions"].items() if pos["in_position"]}

    # =====================
    # トレード履歴 / 成績
    # =====================
    def record_trade_result(self, token_id, result):
        if result in ["win", "loss"]:
            self.state["trade_history"].append({"token_id": token_id, "result": result})
            logging.info(f"Trade result recorded for {token_id}: {result}")
            self._save_state()

    def get_win_rate(self):
        if not self.state["trade_history"]:
            return 0.0
        wins = sum(1 for t in self.state["trade_history"] if t["result"] == "win")
        return (wins / len(self.state["trade_history"])) * 100

    # =====================
    # 日次損益管理
    # =====================
    def update_daily_pnl(self, date_str, realized_usdt=0.0, realized_jpy=0.0, entry_count=0, exit_count=0):
        if date_str not in self.state["daily_pnl"]:
            self.state["daily_pnl"][date_str] = {
                "realized_usdt": 0.0,
                "realized_jpy": 0.0,
                "entry_count": 0,
                "exit_count": 0,
            }
        self.state["daily_pnl"][date_str]["realized_usdt"] += realized_usdt
        self.state["daily_pnl"][date_str]["realized_jpy"] += realized_jpy
        self.state["daily_pnl"][date_str]["entry_count"] += entry_count
        self.state["daily_pnl"][date_str]["exit_count"] += exit_count
        self._save_state()

    def get_daily_pnl(self, date_str):
        return self.state["daily_pnl"].get(date_str, {"realized_usdt": 0.0, "realized_jpy": 0.0, "entry_count": 0, "exit_count": 0})

    # =====================
    # スナップショット保存
    # =====================
    def update_last_snapshot(self, snapshot: dict):
        """最新のマーケットスナップショットを保存"""
        self.state["last_snapshot"] = snapshot
        self._save_state()

    def get_last_snapshot(self):
        """直近のスナップショットを取得"""
        return self.state.get("last_snapshot")
