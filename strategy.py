# state_manager.py
import time
import logging

class StateManager:
    def __init__(self, notification_interval=21600): # 6 hours
        self.notified_tokens = {}
        self.positions = {} # {'token_id': {'in_position': True, 'details': {...}}}
        self.trade_history = [] # [{'token_id': str, 'result': 'win'/'loss'}]
        self.pending_signals = {} # {'token_id': {'score': 85, 'entry_price': 50000, ...}}
        self.notification_interval = notification_interval

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
