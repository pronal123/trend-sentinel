# trading_executor.py
import logging
import pandas_ta as ta
# ... (ccxtとosのインポート)

class TradingExecutor:
    # __init__ は前回と同様
    def __init__(self, state_manager):
        # ...
    
    def open_long_position(self, token_id, series, trade_amount_usd=100.0):
        if self.state.has_position(token_id): return
        
        # 1. 動的な利確(TP)・損切(SL)ポイントを計算
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            
            # リスク:リワード比 1:2
            stop_loss = current_price - (atr * 1.5)
            take_profit = current_price + (atr * 3.0)
            logging.info(f"Calculated exit points for {token_id}: TP=${take_profit:.4f}, SL=${stop_loss:.4f}")
        except Exception as e:
            logging.error(f"Could not calculate exit points: {e}"); return

        # 2. 注文実行 (シミュレーション)
        logging.warning(f"--- SIMULATION: Executing LONG for {token_id} at ${current_price:.4f} ---")
        
        # 3. ポジション情報を状態として記録
        position_details = {
            'entry_price': current_price,
            'take_profit': take_profit,
            'stop_loss': stop_loss
        }
        self.state.set_position(token_id, True, position_details)

    def close_long_position(self, token_id, reason=""):
        if not self.state.has_position(token_id): return
        logging.warning(f"--- SIMULATION: Executing SELL for {token_id} due to {reason} ---")
        self.state.set_position(token_id, False, None)

    def check_active_positions(self, data_aggregator):
        """保有中の全ポジションを監視し、TP/SLに達していたら決済する"""
        active_positions = self.state.get_all_positions()
        if not active_positions: return

        logging.info(f"Checking {len(active_positions)} active position(s)...")
        for token_id, details in active_positions.items():
            try:
                current_price = data_aggregator.get_latest_price(token_id)
                if current_price >= details['take_profit']:
                    logging.info(f"✅ TAKE PROFIT triggered for {token_id} at ${current_price:.4f}")
                    self.close_long_position(token_id, reason="TAKE_PROFIT")
                elif current_price <= details['stop_loss']:
                    logging.info(f"🛑 STOP LOSS triggered for {token_id} at ${current_price:.4f}")
                    self.close_long_position(token_id, reason="STOP_LOSS")
            except Exception as e:
                logging.error(f"Could not check position for {token_id}: {e}")
