# trading_executor.py
import os
import logging
import ccxt
import pandas_ta as ta

class TradingExecutor:
    """
    取引の実行、ポジション管理、動的な撤退判断を担当するクラス。
    リアルタイムの残高を常に考慮する。
    """
    def __init__(self, state_manager):
        self.state = state_manager
        self.exchange = None
        self.ticker_map = {}

        # ... (APIキー読み込みとccxt初期化は変更なし)

    def get_account_balance_usd(self):
        """取引所の利用可能なUSD(T)残高をリアルタイムで取得する"""
        if not self.exchange:
            logging.warning("Exchange not initialized. Returning dummy balance.")
            return 10000.0
        try:
            balance = self.exchange.fetch_balance()
            # USDT, USDCなど主要なステーブルコインの利用可能残高を返す
            usd_balance = balance.get('USDT', {}).get('free', 0.0)
            return usd_balance
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}")
            return 0.0 # エラー時は0を返し、新規取引を防ぐ

    def open_long_position(self, token_id, series, reason="", trade_amount_usd=100.0, notifier=None, win_rate=0.0):
        if self.state.has_position(token_id): return
        
        ticker = self.get_ticker_for_id(token_id)
        if not ticker: return

        # --- ▼▼▼ リアルタイム残高チェック ▼▼▼ ---
        available_balance = self.get_account_balance_usd()
        
        if available_balance < 10: # 最低取引額（例: 10ドル）を下回る場合は中止
            logging.warning(f"Insufficient balance (${available_balance:.2f}) to open new position. Skipping.")
            return

        # 要求された取引額が利用可能残高を超える場合、取引額を減額
        actual_trade_amount = min(trade_amount_usd, available_balance)
        if actual_trade_amount < trade_amount_usd:
            logging.warning(f"Trade amount adjusted from ${trade_amount_usd} to ${actual_trade_amount:.2f} due to balance limit.")
        # --- ▲▲▲ ここまで ▲▲▲ ---

        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            
            volatility_ratio = (atr / current_price) * 100
            sl_multiplier, tp_multiplier = (1.2, 2.4) if volatility_ratio > 5.0 else (1.5, 3.0)
            
            stop_loss = current_price - (atr * sl_multiplier)
            take_profit = current_price + (atr * tp_multiplier)
        except Exception as e:
            logging.error(f"Could not calculate exit points: {e}"); return

        position_size = actual_trade_amount / current_price
        asset = ticker.split('/')[0]

        # --- 注文実行 (シミュレーション) ---
        logging.warning(f"--- SIMULATION: Executing LONG for {token_id} with ${actual_trade_amount:.2f} ---")
        
        # 注文後の残高をシミュレート
        balance_after_trade = available_balance - actual_trade_amount
        
        # --- ポジション情報を状態として記録 ---
        position_details = {
            'ticker': ticker, 'entry_price': current_price,
            'take_profit': take_profit, 'stop_loss': stop_loss,
            'trade_amount_usd': actual_trade_amount, 'position_size': position_size
        }
        self.state.set_position(token_id, True, position_details)

        # --- 詳細なTelegram通知を送信 ---
        if notifier:
            notification_data = {
                'ticker': ticker, 'asset': asset, 'entry_price': current_price,
                'take_profit': take_profit, 'stop_loss': stop_loss,
                'current_balance': balance_after_trade, # ★注文後の残高を通知
                'position_size': position_size,
                'trade_amount_usd': actual_trade_amount,
                'win_rate': win_rate, 'reason': reason
            }
            notifier.send_new_position_notification(notification_data)

    def close_long_position(self, token_id, close_price, reason=""):
        if not self.state.has_position(token_id): return
        
        details = self.state.get_position_details(token_id)
        
        result = 'win' if close_price > details['entry_price'] else 'loss'
        self.state.record_trade_result(token_id, result)
        
        logging.warning(f"--- SIMULATION: Executing SELL for {token_id} at ${close_price:,.4f} due to {reason} ---")
        
        self.state.set_position(token_id, False, None)

    def check_active_positions(self, data_aggregator):
        # ... (この関数は変更なし)
        pass
