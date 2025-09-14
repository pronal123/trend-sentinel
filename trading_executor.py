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
        
        exchange_id = os.environ.get('EXCHANGE_ID')
        api_key = os.environ.get('EXCHANGE_API_KEY')
        api_secret = os.environ.get('EXCHANGE_SECRET_KEY')
        api_passphrase = os.environ.get('EXCHANGE_API_PASSPHRASE')

        if not all([exchange_id, api_key, api_secret]):
            logging.warning("API credentials not fully set. Running in SIMULATION mode.")
            return

        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {'apiKey': api_key, 'secret': api_secret}
            if api_passphrase: config['password'] = api_passphrase
            self.exchange = exchange_class(config)
            self.load_markets()
            logging.info(f"TradingExecutor initialized successfully with {exchange_id}.")
        except Exception as e:
            logging.error(f"Failed to initialize exchange: {e}")

    def load_markets(self):
        if not self.exchange: return
        try:
            self.exchange.load_markets()
        except Exception as e:
            logging.error(f"Failed to load markets: {e}")

    def get_ticker_for_id(self, coingecko_id):
        # CoinGecko IDから取引所のティッカーを検索（簡易版）
        # 実際の運用ではより堅牢なマッピングが必要です
        return f"{coingecko_id.upper()}/USDT"

    def get_account_balance_usd(self):
        if not self.exchange: return 10000.0
        try:
            balance = self.exchange.fetch_balance()
            return balance.get('USDT', {}).get('free', 0.0)
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}"); return 0.0

    def open_long_position(self, token_id, series, trade_amount_usd, reason="", notifier=None, win_rate=0.0):
        if self.state.has_position(token_id): return
        
        ticker = self.get_ticker_for_id(token_id)
        available_balance = self.get_account_balance_usd()
        
        if available_balance < trade_amount_usd:
            logging.warning(f"Insufficient balance. Skipping."); return
        
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['close'].iloc[-1]
            stop_loss = current_price - (atr * 1.5)
            take_profit = current_price + (atr * 3.0)
            position_size = trade_amount_usd / current_price
            asset = ticker.split('/')[0]

            # --- 本番用の取引ロジック ---
            logging.info(f"Attempting market BUY order for {ticker}, size {position_size:.6f}")
            # order = self.exchange.create_market_buy_order(ticker, position_size) # 実行時はこの行のコメントを外す
            logging.warning(f"--- SIMULATION: Executed LONG for {token_id} ---") # シミュレーションログ

            balance_after_trade = available_balance - trade_amount_usd
            position_details = {'ticker': ticker, 'entry_price': current_price, 'take_profit': take_profit, 'stop_loss': stop_loss, 'position_size': position_size, 'trade_amount_usd': trade_amount_usd}
            self.state.set_position(token_id, True, position_details)

            if notifier:
                notification_data = {'ticker': ticker, 'asset': asset, 'entry_price': current_price, 'take_profit': take_profit, 'stop_loss': stop_loss, 'current_balance': balance_after_trade, 'position_size': position_size, 'trade_amount_usd': trade_amount_usd, 'win_rate': win_rate, 'reason': reason}
                notifier.send_new_position_notification(notification_data)

        except (ccxt.InsufficientFunds, ccxt.NetworkError, ccxt.ExchangeError) as e:
            logging.error(f"Trade failed for {ticker}: {e}")
            if notifier: notifier.send_error_notification(f"取引失敗 ({ticker}): {e}")
        except Exception as e:
            logging.error(f"Unexpected error during position open: {e}")

    def close_long_position(self, token_id, close_price, reason="", notifier=None):
        if not self.state.has_position(token_id): return
        details = self.state.get_position_details(token_id)
        ticker = details['ticker']
        position_size = details['position_size']
        
        try:
            logging.info(f"Attempting market SELL order for {ticker}, size {position_size:.6f}")
            # order = self.exchange.create_market_sell_order(ticker, position_size) # 実行時はこの行のコメントを外す
            logging.warning(f"--- SIMULATION: Executed SELL for {token_id} ---") # シミュレーションログ
            
            result = 'win' if close_price > details['entry_price'] else 'loss'
            self.state.record_trade_result(token_id, result)
            self.state.set_position(token_id, False, None)

            if notifier:
                pnl = (close_price - details['entry_price']) * position_size
                notifier.send_close_position_notification(ticker, reason, result, pnl)
        except Exception as e:
            logging.error(f"Failed to close position for {ticker}: {e}")
            if notifier: notifier.send_error_notification(f"{ticker}の決済に失敗。手動確認が必要です。")

    def check_active_positions(self, data_aggregator, notifier=None):
        active_positions = self.state.get_all_positions()
        if not active_positions: return

        for token_id, details in active_positions.items():
            try:
                current_price = data_aggregator.get_latest_price(token_id)
                if not current_price: continue

                if current_price >= details['take_profit']:
                    self.close_long_position(token_id, current_price, reason="TAKE PROFIT", notifier=notifier)
                elif current_price <= details['stop_loss']:
                    self.close_long_position(token_id, current_price, reason="STOP LOSS", notifier=notifier)
            except Exception as e:
                logging.error(f"Could not check position for {token_id}: {e}")
