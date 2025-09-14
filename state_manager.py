# state_manager.py
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class StateManager:
    """
    シンプルな state 管理（ファイル永続化付き）。
    - positions: dict[token_id] = details
    - trade_history: list of {'time','token_id','result'} where result is 'win'/'loss'
    - win_rate_history: list of {'time','value'}
    """

    def __init__(self, filename="bot_state.json"):
        self.filename = filename
        self._state = {
            "positions": {},
            "trade_history": [],
            "win_rate_history": []
        }
        self.load_state_from_disk()

    # -----------------------
    # Persistence
    # -----------------------
    def save_state_to_disk(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            logger.info(f"Successfully saved state to {self.filename}")
        except Exception as e:
            logger.error(f"Failed to save state to disk: {e}")

    def load_state_from_disk(self):
        if not os.path.exists(self.filename):
            logger.info(f"State file '{self.filename}' not found. Starting with a fresh state.")
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self._state = json.load(f)
            logger.info(f"State loaded from {self.filename}")
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")

    # -----------------------
    # Positions
    # -----------------------
    def set_position(self, token_id, active, details=None):
        """
        details is a dict like {'ticker':..., 'side': 'long', 'entry_price':..., ...}
        if active == False, details may be None and position will be removed
        """
        if active:
            self._state["positions"][token_id] = details or {}
        else:
            if token_id in self._state["positions"]:
                del self._state["positions"][token_id]
        self.save_state_to_disk()

    def has_position(self, token_id):
        return token_id in self._state.get("positions", {})

    def get_position_details(self, token_id):
        return self._state.get("positions", {}).get(token_id)

    def get_all_active_positions(self):
        return self._state.get("positions", {})

    # -----------------------
    # Trade history & win rate
    # -----------------------
    def record_trade_result(self, token_id, result):
        """
        result: 'win' or 'loss'
        """
        now = datetime.utcnow().isoformat() + "Z"
        self._state.setdefault("trade_history", []).append({
            "time": now,
            "token_id": token_id,
            "result": result
        })
        # update win rate snapshot
        self._update_win_rate_history()
        self.save_state_to_disk()

    def _update_win_rate_history(self):
        # compute current win rate from trade_history and append a snapshot
        history = self._state.get("trade_history", [])
        wins = sum(1 for t in history if t.get("result") == "win")
        total = len(history)
        rate = round((wins / total) * 100, 2) if total > 0 else 0.0
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        self._state.setdefault("win_rate_history", []).append({
            "time": now,
            "value": rate
        })

    def get_win_rate(self):
        # latest value if exists, else compute from trade_history
        wr_hist = self._state.get("win_rate_history", [])
        if wr_hist:
            return wr_hist[-1].get("value", 0.0)
        # fallback compute
        history = self._state.get("trade_history", [])
        wins = sum(1 for t in history if t.get("result") == "win")
        total = len(history)
        return round((wins / total) * 100, 2) if total > 0 else 0.0

    def get_win_rate_history(self):
        hist = self._state.get("win_rate_history", [])
        return {"timestamps": [h["time"] for h in hist], "values": [h["value"] for h in hist]}

    # -----------------------
    # Utility for debugging
    # -----------------------
    def reset_state(self):
        self._state = {"positions": {}, "trade_history": [], "win_rate_history": []}
        self.save_state_to_disk()
