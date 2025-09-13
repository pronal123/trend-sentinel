# trading.py
import os
import logging
import ccxt

class TradingBot:
    """
    取引の実行と状態管理を担当するクラス。
    ccxtライブラリを使用し、様々な取引所に対応可能。
    """
    def __init__(self, ticker='BTC/USDT', trade_amount_usd=100.0):
        self.ticker = ticker
        self.trade_amount_usd = trade_amount_usd # 1回の取引あたりのUSD金額
        self.in_position = False # 現在、資産を保有しているかどうかの状態

        # --- 環境変数から設定を読み込み ---
        exchange_id = os.environ.get('EXCHANGE_ID') # 例: 'binance', 'bybit', 'bitbank'
        api_key = os.environ.get('EXCHANGE_API_KEY')
        api_secret = os.environ.get('EXCHANGE_API_SECRET')

        if not all([exchange_id, api_key, api_secret]):
            logging.warning("API keys/Exchange ID are not fully set. Running in simulation mode.")
            self.exchange = None
            return

        # --- CCXTで取引所インスタンスを作成 ---
        try:
            exchange_class = getattr(ccxt, exchange_id)
            self.exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                # テストネットを使いたい場合は以下の設定を有効化
                # 'options': {
                #     'defaultType': 'future', # or 'spot'
                #     'adjustForTimeDifference': True,
                # },
                # 'urls': {
                #     'api': {
                #         'public': 'https://api-testnet.bybit.com',
                #         'private': 'https://api-testnet.bybit.com',
                #     },
                # },
            })
            # self.exchange.set_sandbox_mode(True) # 取引所がサンドボックスをサポートしている場合
            logging.info(f"Successfully initialized with {exchange_id}.")
            self.check_initial_position()

        except Exception as e:
            logging.error(f"Failed to initialize exchange: {e}")
            self.exchange = None

    def check_initial_position(self):
        """起動時に現在のポジションを確認する"""
        try:
            balance = self.exchange.fetch_balance()
            # BTC/USDT の場合、'BTC' の残高を確認
            asset = self.ticker.split('/')[0] 
            if asset in balance and balance[asset]['total'] > 0:
                self.in_position = True
                logging.info(f"Initial position check: Currently holding {balance[asset]['total']} {asset}.")
            else:
                self.in_position = False
                logging.info(f"Initial position check: No position held for {asset}.")
        except Exception as e:
            logging.error(f"Could not check initial position: {e}")
            self.in_position = False
            
    def execute_buy_order(self):
        """買い注文を実行する"""
        if not self.exchange:
            logging.warning("--- SIMULATION: Executed BUY order. ---")
            self.in_position = True
            return

        if self.in_position:
            logging.info("Already in position. Skipping BUY order.")
            return

        try:
            logging.info(f"Placing market BUY order for {self.ticker} amount {self.trade_amount_usd} USD.")
            # USD建ての金額で市場価格で買える量を指定して発注
            order = self.exchange.create_market_buy_order_with_cost(self.ticker, self.trade_amount_usd)
            logging.info(f"BUY order successful. Order ID: {order['id']}")
            self.in_position = True

        except ccxt.InsufficientFunds as e:
            logging.error(f"BUY order failed: Insufficient funds. {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during BUY order: {e}")

    def execute_sell_order(self):
        """売り注文を実行する"""
        if not self.exchange:
            logging.warning("--- SIMULATION: Executed SELL order. ---")
            self.in_position = False
            return

        if not self.in_position:
            logging.info("Not in a position. Skipping SELL order.")
            return

        try:
            # 現在保有している資産の量を取得
            balance = self.exchange.fetch_balance()
            asset = self.ticker.split('/')[0]
            amount_to_sell = balance[asset]['free'] # 取引可能な全量を指定

            if amount_to_sell <= 0:
                logging.warning("No sellable assets found. Skipping SELL order.")
                return

            logging.info(f"Placing market SELL order for {amount_to_sell} {asset}.")
            order = self.exchange.create_market_sell_order(self.ticker, amount_to_sell)
            logging.info(f"SELL order successful. Order ID: {order['id']}")
            self.in_position = False

        except ccxt.InsufficientFunds as e:
            logging.error(f"SELL order failed: Insufficient funds. {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during SELL order: {e}")
