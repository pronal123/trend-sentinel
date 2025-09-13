# trading_executor.py
# ... (前回と同様の__init__部分)

class TradingExecutor:
    # ...
    def execute_long(self, token_id, series, trade_amount_usd=100.0):
        if self.state.has_position(token_id): return
        
        ticker = self.get_ticker_for_id(token_id)
        if not ticker: return
            
        # --- 動的な利確・損切りポイントの計算 ---
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            
            # 損小利大の原則 (リスク:リワード比 1:2)
            stop_loss_price = current_price - (atr * 1.5) # 損切りライン (ATRの1.5倍下に設定)
            take_profit_price = current_price + (atr * 3.0) # 利確ライン (ATRの3.0倍上に設定)
            
            logging.info(f"Calculated exit points for {ticker}: TP=${take_profit_price:.4f}, SL=${stop_loss_price:.4f}")

        except Exception as e:
            logging.error(f"Could not calculate ATR for exit points: {e}")
            return

        # --- 注文実行 ---
        if not self.exchange:
            logging.warning(f"--- SIMULATION: Executed LONG for {token_id}. ---")
        else:
            try:
                # ... (実際の買い注文ロジック)
                pass
            except Exception as e:
                logging.error(f"Failed to execute LONG for {ticker}: {e}")
                return

        # ポジション情報（利確・損切り価格を含む）を記録
        self.state.set_position(token_id, True, {
            'entry_price': current_price,
            'take_profit': take_profit_price,
            'stop_loss': stop_loss_price
        })

    def check_and_execute_exit(self, token_id, current_price):
        """保有ポジションの利確・損切りをチェックして実行する"""
        position_details = self.state.get_position_details(token_id)
        if not position_details: return
        
        # 利確チェック
        if current_price >= position_details['take_profit']:
            logging.info(f"✅ TAKE PROFIT triggered for {token_id} at ${current_price:.4f}")
            self.execute_short(token_id) # 全量売却
            
        # 損切りチェック
        elif current_price <= position_details['stop_loss']:
            logging.info(f"🛑 STOP LOSS triggered for {token_id} at ${current_price:.4f}")
            self.execute_short(token_id) # 全量売却
