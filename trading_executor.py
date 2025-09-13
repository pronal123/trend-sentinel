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
        self.exchange = None
        self.ticker_map = {}

        exchange_id = os.environ.get('EXCHANGE_ID')
        api_key = os.environ.get('EXCHANGE_API_KEY')
        api_secret = os.environ.get('EXCHANGE_SECRET_KEY')
        api_passphrase = os.environ.get('EXCHANGE_API_PASSPHRASE')

        if not all([exchange_id, api_key, api_secret]):
            logging.warning("API credentials not fully set. Running in SIMULATION mode."); return

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
            markets = self.exchange.load_markets()
            for ticker, market_info in markets.items():
                if 'baseId' in market_info:
                    self.ticker_map[market_info['baseId'].lower()] = ticker
        except Exception as e:
            logging.error(f"Failed to load markets: {e}")

    def get_ticker_for_id(self, coingecko_id):
        return self.ticker_map.get(coingecko_id.lower())

    def get_account_balance_usd(self):
        if not self.exchange: return 10000.0
        try:
            return self.exchange.fetch_balance().get('USD', {}).get('total', 10000.0)
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}"); return None

    def open_long_position(self, token_id, series, reason="", trade_amount_usd=100.0, notifier=None, win_rate=0.0):
        if self.state.has_position(token_id): return
        ticker = self.get_ticker_for_id(token_id)
        if not ticker: return
            
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            
            # --- パラメータの動的調整 ---
            volatility_ratio = (atr / current_price) * 100
            stop_loss_multiplier, take_profit_multiplier = (1.2, 2.4) if volatility_ratio > 5.0 else (1.5, 3.0)
            logging.info(f"Volatility is {volatility_ratio:.2f}%. Using multipliers: SL={stop_loss_multiplier}, TP={take_profit_multiplier}")

            stop_loss = current_price - (atr * stop_loss_multiplier)
            take_profit = current_price + (atr * take_profit_multiplier)
        except Exception as e:
            logging.error(f"Could not calculate exit points: {e}"); return

        current_balance = self.get_account_balance_usd()
        if not current_balance: return
        position_size = trade_amount_usd / current_price
        asset = ticker.split('/')[0]

        logging.warning(f"--- SIMULATION: Executing LONG for {token_id} at ${current_price:,.4f} ---")
        
        position_details = {
            'ticker': ticker, 'entry_price': current_price,
            'take_profit': take_profit, 'stop_loss': stop_loss
        }
        self.state.set_position(token_id, True, position_details)

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
        result = 'win' if close_price > details['entry_price'] else 'loss'
        self.state.record_trade_result(token_id, result)
        logging.warning(f"--- SIMULATION: Executing SELL for {token_id} at ${close_price:,.4f} due to {reason} ---")
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
