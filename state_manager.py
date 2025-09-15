# state_manager.py
import time
import logging
import json
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

class StateManager:
    def __init__(self, filename="state.json", notification_interval=21600): # 6h
        self.filename = filename
        self.notification_interval = notification_interval

        # 状態保持
        self.state = {
            "balance": 0.0,
            "positions": {},      # {'token_id': {'in_position': True, 'details': {...}}}
            "trade_history": [],  # [{'token_id': str, 'result': 'win'/'loss'}]
            "pending_signals": {},# {'token_id': {...}}
            "events": [],         # 通知用イベントログ
            "last_id": 0,         # イベントID
            "daily_pnl": {},      # {日付: 損益合計}
            "trade_counts": {},   # {日付: {"entry": n, "close": m}}
            "notified_tokens": {} # 通知済み管理
        }
        self.load()

    # --- 永続化 ---
    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"State load error: {e}")

    def save(self):
        try:
            with open(self.filename, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"State save error: {e}")

    # --- 残高 ---
    def update_balance(self, balance):
        self.state["balance"] = balance
        self.save()

    def get_balance(self):
        return self.state.get("balance", 0.0)

    # --- ポジション ---
    def set_position(self, token_id, status, details=None):
        self.state["positions"][token_id] = {"in_position": status, "details": details}
        logging.info(f"Position for {token_id} set to {status}.")
        self.save()

    def has_position(self, token_id):
        return self.state["positions"].get(token_id, {}).get("in_position", False)

    def get_position_details(self, token_id):
        return self.state["positions"].get(token_id, {}).get("details")

    def get_all_positions(self):
        return {
            token_id: pos["details"]
            for token_id, pos in self.state["positions"].items()
            if pos.get("in_position", False)
        }

    def close_position(self, token_id):
        if token_id in self.state["positions"]:
            del self.state["positions"][token_id]
            self.save()

    # --- シグナル ---
    def add_pending_signal(self, token_id, details):
        self.state["pending_signals"][token_id] = details
        logging.info(f"Signal for {token_id} is now PENDING CONFIRMATION.")
        self.save()

    def get_and_clear_pending_signals(self):
        pending = self.state["pending_signals"]
        self.state["pending_signals"] = {}
        self.save()
        return pending

    # --- 勝率 ---
    def record_trade_result(self, token_id, result):
        if result in ["win", "loss"]:
            self.state["trade_history"].append({"token_id": token_id, "result": result})
            logging.info(f"Trade result recorded for {token_id}: {result}")
            self.save()

    def get_win_rate(self):
        if not self.state["trade_history"]:
            return 0.0
        wins = sum(1 for t in self.state["trade_history"] if t["result"] == "win")
        total = len(self.state["trade_history"])
        return (wins / total) * 100

    # --- イベントログ ---
    def log_event(self, event: dict):
        self.state["last_id"] += 1
        event["id"] = self.state["last_id"]
        event["timestamp"] = time.time()
        self.state["events"].append(event)

        date_str = datetime.now(JST).strftime("%Y-%m-%d")

        if event["type"] == "entry":
            self.state["trade_counts"].setdefault(date_str, {"entry": 0, "close": 0})
            self.state["trade_counts"][date_str]["entry"] += 1

        elif event["type"] == "close":
            self.state["trade_counts"].setdefault(date_str, {"entry": 0, "close": 0})
            self.state["trade_counts"][date_str]["close"] += 1
            pnl = event.get("pnl", 0.0)
            self.state["daily_pnl"][date_str] = self.state["daily_pnl"].get(date_str, 0.0) + pnl

        self.save()

    def get_trade_events(self):
        return self.state.get("events", [])

    def get_today_pnl(self):
        date_str = datetime.now(JST).strftime("%Y-%m-%d")
        return self.state["daily_pnl"].get(date_str, 0.0)

    def get_today_trade_counts(self):
        date_str = datetime.now(JST).strftime("%Y-%m-%d")
        return self.state["trade_counts"].get(date_str, {"entry": 0, "close": 0})
