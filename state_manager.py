# state_manager.py (追加・改良部分)
import json
import os
import logging

class StateManager:
    def __init__(self, state_file='bot_state.json', ...):
        # ... (既存の初期化) ...
        self.state_file = state_file
        self.watchlist = {} # {'token_id': {'score': 75, 'last_seen': timestamp}}

    def save_state_to_disk(self):
        """現在のBOTの状態をJSONファイルに保存する"""
        try:
            state_data = {
                'positions': self.positions,
                'notified_tokens': self.notified_tokens,
                'trade_history': self.trade_history,
                'watchlist': self.watchlist
            }
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            logging.info(f"Successfully saved state to {self.state_file}")
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def load_state_from_disk(self):
        """ファイルからBOTの状態を復元する"""
        if not os.path.exists(self.state_file):
            logging.warning("State file not found. Starting with a fresh state.")
            return
        try:
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            self.positions = state_data.get('positions', {})
            self.notified_tokens = state_data.get('notified_tokens', {})
            self.trade_history = state_data.get('trade_history', {'wins': 0, 'losses': 0})
            self.watchlist = state_data.get('watchlist', {})
            logging.info(f"Successfully loaded state from {self.state_file}. Positions: {len(self.positions)}")
        except Exception as e:
            logging.error(f"Failed to load state: {e}")

    def update_watchlist(self, token_id, score):
        # ウォッチリストの更新
        self.watchlist[token_id] = {'score': score, 'last_seen': time.time()}

    def get_watchlist(self):
        # 古いエントリを除外して返す (例: 24時間以上更新がないものは削除)
        current_time = time.time()
        self.watchlist = {
            tid: data for tid, data in self.watchlist.items() 
            if current_time - data['last_seen'] < 86400 
        }
        return self.watchlist
