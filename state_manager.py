# state_manager.py
import json
import os
from datetime import datetime, timezone
import threading
import logging

LOCK = threading.Lock()

class StateManager:
    def __init__(self, state_file="bot_state.json"):
        self.state_file = state_file
        self.state = {
            "positions": {},
            "trade_history": [],
            "ai_comments_cache": {},   # 銘柄ごとのキャッシュ（将来活用可能）
            "chain_perf_cache": {"data": {}, "timestamp": 0}
        }
        self._load_state()

    # ------------------------
    # 永続化
    # ------------------------
    def _load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                logging.info(f"Loaded state from {self.state_file}")
            else:
                logging.info(f"State file {self.state_file} not found. Using fresh state.")
        except Exception as e:
            logging.error(f"Failed to load state: {e}")

    def save_state(self):
        try:
            with LOCK:
                with open(self.state_file, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved state to {self.state_file}")
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    # ------------------------
    # ポジション管理
    # ------------------------
    def set_position(self, token_id: str, active: bool, details: dict):
        if active:
            self.state.setdefault("positions", {})[token_id] = details
        else:
            self.state.setdefault("positions", {}).pop(token_id, None)
        self.save_state()

    def get_all_active_positions(self) -> dict:
        return self.state.get("positions", {})

    def has_position(self, token_id: str) -> bool:
        return token_id in self.state.get("positions", {})

    def get_position_details(self, token_id: str):
        return self.state.get("positions", {}).get(token_id)

    # ------------------------
    # トレード履歴 / 勝率
    # ------------------------
    def record_trade_result(self, token_id: str, result: str):
        # result: 'win' or 'loss'
        self.state.setdefault("trade_history", []).append({
            "token": token_id,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self.save_state()

    def get_win_rate(self) -> float:
        history = self.state.get("trade_history", [])
        if not history:
            return 0.0
        wins = sum(1 for h in history if h.get("result") == "win")
        return (wins / len(history)) * 100.0

    # ------------------------
    # AIコメントキャッシュ（銘柄ごと）
    # ------------------------
    def update_ai_comment(self, symbol: str, comment: str):
        self.state.setdefault("ai_comments_cache", {})[symbol] = {
            "comment": comment,
            "last_update": datetime.now(timezone.utc).isoformat()
        }
        self.save_state()

    def get_ai_comment(self, symbol: str):
        return self.state.get("ai_comments_cache", {}).get(symbol)

    def get_all_ai_comments(self):
        return self.state.get("ai_comments_cache", {})

    # ------------------------
    # チェーンパフォーマンスキャッシュ（5分キャッシュ用）
    # ------------------------
    def get_chain_perf_cache(self):
        return self.state.get("chain_perf_cache", {"data": {}, "timestamp": 0})

    def update_chain_perf_cache(self, data: dict, timestamp: float):
        self.state["chain_perf_cache"] = {"data": data, "timestamp": timestamp}
        self.save_state()
