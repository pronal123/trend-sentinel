# trading_executor.py
import os
import logging
import ccxt
import pandas_ta as ta

class TradingExecutor:
    """
    取引の実行、ポジション管理、動的な撤退判断を担当するクラス。
    """
    def __init__(self, state_manager):
        self.state = state_manager
        # ... (APIキー読み込みとccxt初期化は前回と同様)

    def get_account_balance_usd(self):
        """取引所の総資産（USD換算）を取得する"""
        if not self.exchange: return 10000.0 # シミュレーション用のダミー残高
        try:
            balance = self.exchange.fetch_balance()
            # ここでは簡略化のためUSD残高のみを返す
            return balance['USD']['total']
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}")
            return None

    def open_long_position(self, token_id, series, reason="", trade_amount_usd=100.0, notifier=None, win_rate=0.0):
        if self.state.has_position(token_id): return
        
        ticker = self.get_ticker_for_id(token_id)
        if not ticker: return
            
        # 1. 動的な利確(TP)・損切(SL)ポイントを計算
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            stop_loss = current_price - (atr * 1.5)
            take_profit = current_price + (atr * 3.0)
        except Exception as e:
            logging.error(f"Could not calculate exit points: {e}"); return

        # 2. 残高とポジションサイズを取得
        current_balance = self.get_account_balance_usd()
        if not current_balance: return
        
        position_size = trade_amount_usd / current_price
        asset = ticker.split('/')[0]

        # 3. 注文実行 (シミュレーション)
        logging.warning(f"--- SIMULATION: Executing LONG for {token_id} at ${current_price:.4f} ---")
        
        # 4. ポジション情報を状態として記録
        position_details = {
            'ticker': ticker, 'entry_price': current_price,
            'take_profit': take_profit, 'stop_loss': stop_loss
        }
        self.state.set_position(token_id, True, position_details)

        # 5. 詳細なTelegram通知を送信
        if notifier:
            notification_data = {
                'ticker': ticker, 'asset': asset, 'entry_price': current_price,
                'take_profit': take_profit, 'stop_loss': stop_loss,
                'current_balance': current_balance, 'position_size': position_size,
                'trade_amount_usd': trade_amount_usd, 'win_rate': win_rate, 'reason': reason
            }
            notifier.send_new_position_notification(notification_data)

    def close_long_position(self, token_id, close_price, reason=""):
        if not self.state.has_position(token_id): return
        
        details = self.state.get_position_details(token_id)
        
        # 1. 勝敗を判断して記録
        result = 'win' if close_price > details['entry_price'] else 'loss'
        self.state.record_trade_result(token_id, result)
        
        # 2. 注文実行 (シミュレーション)
        logging.warning(f"--- SIMULATION: Executing SELL for {token_id} due to {reason} ---")
        
        # 3. ポジション情報をクリア
        self.state.set_position(token_id, False, None)

    def check_active_positions(self, data_aggregator):
        active_positions = self.state.get_all_positions()
        if not active_positions: return

        logging.info(f"Checking {len(active_positions)} active position(s)...")
        for token_id, details in active_positions.items():
            try:
                current_price = data_aggregator.get_latest_price(token_id)
                if not current_price: continue

                if current_price >= details['take_profit']:
                    self.close_long_position(token_id, current_price, reason="TAKE_PROFIT")
                elif current_price <= details['stop_loss']:
                    self.close_long_position(token_id, current_price, reason="STOP_LOSS")
            except Exception as e:
                logging.error(f"Could not check position for {token_id}: {e}")
