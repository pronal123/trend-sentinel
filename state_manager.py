# state_manager.py
import time
import logging

class StateManager:
    """
    BOTの状態（通知履歴、ポジション、取引履歴）を一元管理するクラス。
    """
    def __init__(self, notification_interval=21600): # 6 hours in seconds
        self.notified_tokens = {} # {'token_symbol': timestamp}
        self.positions = {} # {'coingecko_id': {'in_position': True/False, 'details': {}}}
        self.trade_history = [] # [{'token_id': str, 'result': 'win'/'loss'}]
        self.notification_interval = notification_interval

    # --- 通知管理 ---
    def can_notify(self, token_symbol):
        """指定されたトークンが通知可能か（前回の通知から一定時間経過したか）を判定する"""
        last_notified = self.notified_tokens.get(token_symbol)
        return not last_notified or (time.time() - last_notified > self.notification_interval)

    def record_notification(self, df):
        """通知したトークンとその時刻を記録する"""
        for symbol in df['symbol']:
            self.notified_tokens[symbol] = time.time()
            
    # --- ポジション管理 ---
    def has_position(self, token_id):
        """指定されたトークンのポジションを現在保有しているか"""
        return self.positions.get(token_id, {}).get('in_position', False)

    def set_position(self, token_id, status, details=None):
        """ポジションの状態（保有/非保有）と詳細情報を設定する"""
        self.positions[token_id] = {'in_position': status, 'details': details}
        logging.info(f"Position for {token_id} set to {status}.")

    def get_position_details(self, token_id):
        """指定されたトークンのポジション詳細（利確・損切価格など）を取得する"""
        return self.positions.get(token_id, {}).get('details')

    def get_all_positions(self):
        """現在保有している全てのポジション情報を取得する"""
        return {token_id: pos['details'] for token_id, pos in self.positions.items() if pos['in_position']}

    # --- 勝率管理 ---
    def record_trade_result(self, token_id, result):
        """取引結果（勝ち/負け）を記録する"""
        if result in ['win', 'loss']:
            self.trade_history.append({'token_id': token_id, 'result': result})
            logging.info(f"Trade result recorded for {token_id}: {result}")

    def get_win_rate(self):
        """現在の勝率を計算して返す (%)"""
        if not self.trade_history:
            return 0.0
        
        wins = sum(1 for trade in self.trade_history if trade['result'] == 'win')
        total_trades = len(self.trade_history)
        
        return (wins / total_trades) * 100
