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
            markets = self.exchange.load_markets()
            for ticker, market_info in markets.items():
                if 'baseId' in market_info:
                    self.ticker_map[market_info['baseId'].lower()] = ticker
        except Exception as e:
            logging.error(f"Failed to load markets: {e}")

    def get_ticker_for_id(self, coingecko_id):
        return self.ticker_map.get(coingecko_id.lower())

    def get_account_balance_usd(self):
        if not self.exchange:
            logging.warning("Exchange not initialized. Returning dummy balance.")
            return 10000.0
        try:
            logging.info("Fetching account balance from exchange...")
            balance = self.exchange.fetch_balance()
            total_usd = 0.0
            if 'total' in balance: del balance['total']

            for currency, amounts in balance.items():
                if amounts['total'] > 0:
                    if currency in ['USD', 'USDT', 'USDC', 'DAI', 'BUSD']:
                        total_usd += amounts['total']
                    else:
                        try:
                            ticker = f'{currency}/USDT'
                            price_info = self.exchange.fetch_ticker(ticker)
                            total_usd += amounts['total'] * price_info['last']
                        except (ccxt.BadSymbol, ccxt.ExchangeError):
                            pass
            logging.info(f"Successfully calculated total balance: ${total_usd:,.2f}")
            return total_usd
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}"); return None

    def open_long_position(self, token_id, series, reason="", trade_amount_usd=100.0, notifier=None, win_rate=0.0):
        # ... (この関数は前回と同様)
        pass

    def close_long_position(self, token_id, close_price, reason=""):
        # ... (この関数は前回と同様)
        pass

    def check_active_positions(self, data_aggregator):
        # ... (この関数は前回と同様)
        pass
