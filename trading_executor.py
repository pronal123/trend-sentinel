# trading_executor.py
import os
import logging
import ccxt
import pandas_ta as ta

class TradingExecutor:
    def __init__(self, state_manager):
        self.state = state_manager
        self.exchange = None
        self.ticker_map = {}
        # ... (APIキー読み込みとccxt初期化は変更なし)

    # ... (load_markets, get_ticker_for_id, get_account_balance_usd は変更なし)

    def open_long_position(self, token_id, series, trade_amount_usd, reason="", notifier=None, win_rate=0.0):
        if self.state.has_position(token_id): return
        
        ticker = self.get_ticker_for_id(token_id)
        if not ticker: return
            
        available_balance = self.get_account_balance_usd()
        if available_balance < 10:
            logging.warning(f"Insufficient balance to open position. Skipping."); return
        
        actual_trade_amount = min(trade_amount_usd, available_balance)
        
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['close'].iloc[-1]
            volatility_ratio = (atr / current_price) * 100
            sl_multiplier, tp_multiplier = (1.2, 2.4) if volatility_ratio > 5.0 else (1.5, 3.0)
            stop_loss = current_price - (atr * sl_multiplier)
            take_profit = current_price + (atr * tp_multiplier)
        except Exception as e:
            logging.error(f"Could not calculate exit points: {e}"); return
        
        position_size = actual_trade_amount / current_price
        asset = ticker.split('/')[0]
        
        logging.warning(f"--- SIMULATION: Executing LONG for {token_id} with ${actual_trade_amount:.2f} ---")
        
        position_details = {'ticker': ticker, 'entry_price': current_price, 'take_profit': take_profit, 'stop_loss': stop_loss, 'position_size': position_size, 'trade_amount_usd': actual_trade_amount}
        self.state.set_position(token_id, True, position_details)

        if notifier:
            notification_data = {
                'ticker': ticker, 'asset': asset, 'entry_price': current_price,
                'take_profit': take_profit, 'stop_loss': stop_loss,
                'current_balance': available_balance - actual_trade_amount,
                'position_size': position_size, 'trade_amount_usd': actual_trade_amount,
                'win_rate': win_rate, 'reason': reason
            }
            notifier.send_new_position_notification(notification_data)

    # ... (close_long_position, check_active_positions は変更なし)
