# state_manager.py
import time
import logging
import json
import os

class StateManager:
    """
    BOTの状態（ポジション、通知履歴、取引結果など）を一元管理し、
    ファイルへの保存・復元を行うクラス。
    """
    def __init__(self, state_file='bot_state.json', notification_interval_hours=6):
        self.state_file = state_file
        self.notification_interval = notification_interval_hours * 3600  # 時間を秒に変換
        
        # BOTの状態を保持する変数
        self.notified_tokens = {}  # {'token_symbol': timestamp}
        self.positions = {}        # {'coingecko_id': {'active': True/False, 'details': {...}}}
        self.trade_history = {'wins': 0, 'losses': 0}
        self.watchlist = {}        # {'token_id': {'score': 75, 'last_seen': timestamp}}
        
        logging.info("StateManager initialized.")

    def save_state_to_disk(self):
        """現在のBOTの全ての状態をJSONファイルに保存する"""
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
            logging.warning(f"State file '{self.state_file}' not found. Starting with a fresh state.")
            return
        try:
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            self.positions = state_data.get('positions', {})
            self.notified_tokens = state_data.get('notified_tokens', {})
            self.trade_history = state_data.get('trade_history', {'wins': 0, 'losses': 0})
            self.watchlist = state_data.get('watchlist', {})
            logging.info(f"Successfully loaded state from {self.state_file}. Active Positions: {len(self.get_all_active_positions())}")
        except Exception as e:
            logging.error(f"Failed to load state: {e}")

    # --- 通知管理 ---
    def can_notify(self, token_symbol):
        last_notified = self.notified_tokens.get(token_symbol)
        if not last_notified:
            return True
        return (time.time() - last_notified) > self.notification_interval

    def record_notification(self, df):
        for symbol in df['symbol']:
            self.notified_tokens[symbol] = time.time()
            
    # --- ポジション管理 ---
    def has_position(self, token_id):
        return self.positions.get(token_id, {}).get('active', False)

    def set_position(self, token_id, is_active, details=None):
        self.positions[token_id] = {'active': is_active, 'details': details}
        logging.info(f"Position for {token_id} set to active={is_active}.")

    def get_position_details(self, token_id):
        return self.positions.get(token_id, {}).get('details')

    def get_all_active_positions(self):
        return {token_id: pos['details'] for token_id, pos in self.positions.items() if pos.get('active')}

    # --- 取引結果と勝率 ---
    def record_trade_result(self, token_id, result):
        if result == 'win':
            self.trade_history['wins'] += 1
        else:
            self.trade_history['losses'] += 1
        logging.info(f"Trade result recorded for {token_id}: {result}. Current stats: {self.trade_history}")
        
    def get_win_rate(self):
        total_trades = self.trade_history['wins'] + self.trade_history['losses']
        if total_trades == 0:
            return 50.0 # 取引履歴がない場合はデフォルト50%
        return (self.trade_history['wins'] / total_trades) * 100

    # --- ウォッチリスト管理 ---
    def update_watchlist(self, token_id, score):
        self.watchlist[token_id] = {'score': score, 'last_seen': time.time()}

    def get_watchlist(self):
        current_time = time.time()
        # 24時間以上更新がないものはウォッチリストから削除
        self.watchlist = {
            tid: data for tid, data in self.watchlist.items() 
            if current_time - data['last_seen'] < 86400 
        }
        return self.watchlist
