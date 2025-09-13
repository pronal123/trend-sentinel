# trading_executor.py
import os
import logging
import ccxt

class TradingExecutor:
    def __init__(self, state_manager):
        self.state_manager = state_manager # ポジション情報を共有
        self.ticker_map = {} # CoinGecko IDと取引所ティッカーの対応表

        exchange_id = os.environ.get('EXCHANGE_ID')
        api_key = os.environ.get('EXCHANGE_API_KEY')
        api_secret = os.environ.get('EXCHANGE_API_SECRET')

        if not all([exchange_id, api_key, api_secret]):
            logging.warning("API keys/Exchange ID not set. TradingExecutor running in SIMULATION mode.")
            self.exchange = None
            return

        try:
            exchange_class = getattr(ccxt, exchange_id)
            self.exchange = exchange_class({'apiKey': api_key, 'secret': api_secret})
            logging.info(f"TradingExecutor initialized with {exchange_id}.")
            self.load_markets()
        except Exception as e:
            logging.error(f"Failed to initialize exchange: {e}")
            self.exchange = None

    def load_markets(self):
        try:
            markets = self.exchange.load_markets()
            # 例: 'bitcoin' (coingecko) -> 'BTC/USDT' (取引所) の対応表を作成
            for ticker, market_info in markets.items():
                if 'baseId' in market_info:
                    self.ticker_map[market_info['baseId'].lower()] = ticker
        except Exception as e:
            logging.error(f"Failed to load markets: {e}")

    def get_ticker_for_id(self, coingecko_id):
        return self.ticker_map.get(coingecko_id.lower())

    def execute_long(self, token_id, trade_amount_usd=100.0):
        if not self.exchange:
            logging.warning(f"--- SIMULATION: Executed LONG for {token_id}. ---")
            self.state_manager.set_position(token_id, True)
            return
        
        if self.state_manager.has_position(token_id):
            logging.info(f"Already in position for {token_id}. Skipping LONG.")
            return

        ticker = self.get_ticker_for_id(token_id)
        if not ticker:
            logging.warning(f"Ticker for {token_id} not found on exchange. Skipping.")
            return

        try:
            logging.info(f"Executing LONG (market buy) for {ticker} with cost {trade_amount_usd} USD.")
            order = self.exchange.create_market_buy_order_with_cost(ticker, trade_amount_usd)
            logging.info(f"LONG order successful. Order: {order['id']}")
            self.state_manager.set_position(token_id, True)
        except Exception as e:
            logging.error(f"Failed to execute LONG for {ticker}: {e}")

    def execute_short(self, token_id):
        if not self.exchange:
            logging.warning(f"--- SIMULATION: Executed SHORT for {token_id}. ---")
            self.state_manager.set_position(token_id, False)
            return

        if not self.state_manager.has_position(token_id):
            logging.info(f"Not in a position for {token_id}. Skipping SHORT.")
            return
        
        ticker = self.get_ticker_for_id(token_id)
        if not ticker:
            logging.warning(f"Ticker for {token_id} not found on exchange. Skipping.")
            return
            
        try:
            # 保有量を全量売却
            asset = ticker.split('/')[0]
            balance = self.exchange.fetch_balance()
            amount_to_sell = balance[asset]['free']
            
            if amount_to_sell > 0:
                logging.info(f"Executing SHORT (market sell) for {amount_to_sell} {asset}.")
                order = self.exchange.create_market_sell_order(ticker, amount_to_sell)
                logging.info(f"SHORT order successful. Order: {order['id']}")
                self.state_manager.set_position(token_id, False)
            else:
                logging.warning(f"No sellable assets for {ticker}. Updating position state.")
                self.state_manager.set_position(token_id, False)
        except Exception as e:
            logging.error(f"Failed to execute SHORT for {ticker}: {e}")

