# state_manager.py
import time
import logging

class StateManager:
    def __init__(self, notification_interval=21600):
        self.notified_tokens = {}
        self.positions = {} # {'coingecko_id': {'active': True/False, 'details': {...}}}
        self.notification_interval = notification_interval
        self.trade_history = {'wins': 0, 'losses': 0}

    # ... (通知管理の関数は変更なし) ...
    def can_notify(self, token_symbol):
        # ...
    def record_notification(self, df):
        # ...

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

    def record_trade_result(self, token_id, result):
        if result == 'win':
            self.trade_history['wins'] += 1
        else:
            self.trade_history['losses'] += 1
        logging.info(f"Trade result recorded for {token_id}: {result}. Current stats: {self.trade_history}")
        
    def get_win_rate(self):
        total_trades = self.trade_history['wins'] + self.trade_history['losses']
        if total_trades == 0:
            return 0.0
        return (self.trade_history['wins'] / total_trades) * 100
