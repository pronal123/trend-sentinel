# state_manager.py
import time
import logging

class StateManager:
    def __init__(self, notification_interval=21600): # 6 hours
        self.notified_tokens = {} # {'token_symbol': timestamp}
        self.positions = {} # {'coingecko_id': True/False}
        self.notification_interval = notification_interval

    # --- 通知管理 ---
    def can_notify(self, token_symbol):
        last_notified = self.notified_tokens.get(token_symbol)
        return not last_notified or (time.time() - last_notified > self.notification_interval)

    def record_notification(self, df):
        for symbol in df['symbol']:
            self.notified_tokens[symbol] = time.time()
            
    # --- ポジション管理 ---
    def has_position(self, token_id):
        return self.positions.get(token_id, False)

    def set_position(self, token_id, status):
        self.positions[token_id] = status
        logging.info(f"Position for {token_id} set to {status}.")
