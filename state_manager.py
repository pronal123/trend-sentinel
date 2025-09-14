import json
import os
import logging
from datetime import datetime
import pytz

STATE_FILE = "bot_state.json"


class StateManager:
    def __init__(self):
        self.state = {
            "balance": 10000.0,  # 初期残高 (USDT)
            "positions": {},
            "win_rate": 0.0,
            "trade_results": [],
            "summary": {},
            "balance_history": [],
            "daily_returns": {}
        }
        self.load_state()

    def load_state(self):
        """JSONファイルから状態を読み込む"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    self.state = json.load(f)
                logging.info("State loaded successfully.")
            except Exception as e:
                logging.error(f"Failed to load state: {e}")

    def save_state(self):
        """状態をJSONファイルに保存する"""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    # -------------------------------
    # ポジション管理
    # -------------------------------
    def has_position(self, token_id):
        return token_id in self.state["positions"]

    def set_position(self, token_id, is_open, details=None):
        if is_open:
            self.state["positions"][token_id] = details or {}
        else:
            self.state["positions"].pop(token_id, None)

    def get_position_details(self, token_id):
        return self.state["positions"].get(token_id)

    def get_all_active_positions(self):
        return self.state["positions"]

    # -------------------------------
    # トレード履歴と勝率管理
    # -------------------------------
    def record_trade_result(self, token_id, result, pnl=0.0):
        """トレード結果を記録し、勝率と残高を更新する"""
        timestamp = datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")
        self.state["trade_results"].append({"token": token_id, "result": result, "pnl": pnl, "time": timestamp})

        # 残高更新
        self.state["balance"] += pnl

        # バランス履歴更新
        self.state["balance_history"].append({
            "time": timestamp,
            "balance": self.state["balance"]
        })

        # 勝率更新
        wins = sum(1 for t in self.state["trade_results"] if t["result"] == "win")
        total = len(self.state["trade_results"])
        self.state["win_rate"] = (wins / total) * 100 if total > 0 else 0.0

        # 日次リターン集計
        today = datetime.now(pytz.timezone("Asia/Tokyo")).strftime("%Y-%m-%d")
        if today not in self.state["daily_returns"]:
            self.state["daily_returns"][today] = {"pnl_usdt": 0.0, "return_pct": 0.0}

        self.state["daily_returns"][today]["pnl_usdt"] += pnl
        start_balance = 10000.0
        if len(self.state["balance_history"]) > 1:
            start_balance = self.state["balance_history"][0]["balance"]
        current_balance = self.state["balance"]
        self.state["daily_returns"][today]["return_pct"] = round(
            (current_balance - start_balance) / start_balance * 100, 2
        )

        self.save_state()

    def get_win_rate(self):
        return self.state.get("win_rate", 0.0)

    # -------------------------------
    # サマリー更新
    # -------------------------------
    def update_summary(self, summary_dict):
        self.state["summary"] = summary_dict

    # -------------------------------
    # /status 用スナップショット
    # -------------------------------
    def get_state_snapshot(self):
        """/status で返すデータをまとめて取得"""
        return {
            "balance": self.state.get("balance", 0.0),
            "win_rate": self.state.get("win_rate", 0.0),
            "positions": self.state.get("positions", {}),
            "summary": self.state.get("summary", {}),
            "balance_history": self.state.get("balance_history", []),
            "daily_returns": self.state.get("daily_returns", {}),
            "trade_results": self.state.get("trade_results", [])
        }
