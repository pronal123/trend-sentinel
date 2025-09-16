# state_manager.py
import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

class StateManager:
    def __init__(self, state_file="state.json", notification_interval=21600):
        self.state_file = state_file
        self.notification_interval = notification_interval
        self.last_snapshot = None  # ← 追加
        self.notified_tokens = {}
        self.positions = {}  # {'token_id': {'in_position': True, 'details': {...}}}
        self.trade_history = []  # [{'token_id': str, 'result': 'win'/'loss'}]
        self.pending_signals = {}  # {'token_id': {...}}
        self.entry_count = 0
        self.exit_count = 0
        self.realized_pnl = []  # [{'timestamp': 'YYYY-MM-DD HH:MM:SS', 'pnl': float}]
        self.load_state()

    def add_pending_signal(self, token_id, details):
        self.pending_signals[token_id] = details
        logging.info(f"Signal for {token_id} is now PENDING CONFIRMATION.")

    def get_and_clear_pending_signals(self):
        pending = self.pending_signals
        self.pending_signals = {}
        return pending

    def has_position(self, token_id):
        return self.positions.get(token_id, {}).get('in_position', False)

    def set_position(self, token_id, status, details=None):
        self.positions[token_id] = {'in_position': status, 'details': details}
        logging.info(f"Position for {token_id} set to {status}.")

    def get_position_details(self, token_id):
        return self.positions.get(token_id, {}).get('details')

    def get_all_positions(self):
        return {token_id: pos['details'] for token_id, pos in self.positions.items() if pos['in_position']}

    def record_trade_result(self, token_id, result):
        if result in ['win', 'loss']:
            self.trade_history.append({'token_id': token_id, 'result': result})
            logging.info(f"Trade result recorded for {token_id}: {result}")

    def get_win_rate(self):
        if not self.trade_history: return 0.0
        wins = sum(1 for trade in self.trade_history if trade['result'] == 'win')
        total_trades = len(self.trade_history)
        return (wins / total_trades) * 100

    # === ここを追加 ===
    def update_last_snapshot(self, market_data, balance, positions):
        """
        最新の状態をスナップショットとして保存
        market_data: dict (テクニカル指標や価格情報)
        balance: dict (Bitgetの口座残高 fetch_balance の結果)
        positions: list (Bitgetのポジション情報 fetch_positions の結果)
        """
        self.last_snapshot = {
            "market_data": market_data,
            "balance": balance,
            "positions": positions,
            "timestamp": time.time()
        }

    def get_last_snapshot(self):
        """保存されたスナップショットを取得"""
        return self.last_snapshot

    # ---------- state persistence ----------
    def save_state(self):
        try:
            state = {
                "notified_tokens": self.notified_tokens,
                "positions": self.positions,
                "trade_history": self.trade_history,
                "pending_signals": self.pending_signals,
                "entry_count": self.entry_count,
                "exit_count": self.exit_count,
                "realized_pnl": self.realized_pnl,
            }
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            self.notified_tokens = state.get("notified_tokens", {})
            self.positions = state.get("positions", {})
            self.trade_history = state.get("trade_history", [])
            self.pending_signals = state.get("pending_signals", {})
            self.entry_count = state.get("entry_count", 0)
            self.exit_count = state.get("exit_count", 0)
            self.realized_pnl = state.get("realized_pnl", [])
        except Exception as e:
            logging.error(f"Failed to load state: {e}")

    # ---------- position management ----------
    def add_pending_signal(self, token_id, details):
        self.pending_signals[token_id] = details
        self.save_state()
        logging.info(f"Signal for {token_id} is now PENDING CONFIRMATION.")

    def get_and_clear_pending_signals(self):
        pending = self.pending_signals
        self.pending_signals = {}
        self.save_state()
        return pending

    def has_position(self, token_id):
        return self.positions.get(token_id, {}).get("in_position", False)

    def set_position(self, token_id, status, details=None):
        self.positions[token_id] = {"in_position": status, "details": details}
        self.save_state()
        logging.info(f"Position for {token_id} set to {status}.")

    def get_position_details(self, token_id):
        return self.positions.get(token_id, {}).get("details")

    def get_all_positions(self):
        return {t: pos["details"] for t, pos in self.positions.items() if pos["in_position"]}

    # ---------- trade stats ----------
    def record_trade_result(self, token_id, result):
        if result in ["win", "loss"]:
            self.trade_history.append({"token_id": token_id, "result": result})
            self.save_state()
            logging.info(f"Trade result recorded for {token_id}: {result}")

    def get_win_rate(self):
        if not self.trade_history:
            return 0.0
        wins = sum(1 for trade in self.trade_history if trade["result"] == "win")
        total_trades = len(self.trade_history)
        return (wins / total_trades) * 100

    # ---------- counters ----------
    def increment_entry(self):
        self.entry_count += 1
        self.save_state()

    def increment_exit(self):
        self.exit_count += 1
        self.save_state()

    def get_trade_counts(self):
        return self.entry_count, self.exit_count

    # ---------- PnL ----------
    def record_realized_pnl(self, pnl_usd: float):
        now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        self.realized_pnl.append({"timestamp": now, "pnl": pnl_usd})
        self.save_state()

    def get_daily_pnl(self):
        today = datetime.now(JST).strftime("%Y-%m-%d")
        return sum(r["pnl"] for r in self.realized_pnl if r["timestamp"].startswith(today))
