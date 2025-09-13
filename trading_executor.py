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
        """
        コンストラクタ。状態管理マネージャーを受け取り、取引所APIを初期化する。
        """
        self.state = state_manager
        self.exchange = None
        self.ticker_map = {}

        # --- 環境変数からAPIキー等を安全に読み込み ---
        exchange_id = os.environ.get('EXCHANGE_ID')
        api_key = os.environ.get('EXCHANGE_API_KEY')
        api_secret = os.environ.get('EXCHANGE_SECRET_KEY')
        api_passphrase = os.environ.get('EXCHANGE_API_PASSPHRASE')

        if not all([exchange_id, api_key, api_secret]):
            logging.warning("API credentials or Exchange ID are not fully set. Running in SIMULATION mode.")
            return

        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {'apiKey': api_key, 'secret': api_secret}
            if api_passphrase:
                config['password'] = api_passphrase # Bitgetなどのパスフレーズに対応

            self.exchange = exchange_class(config)
            self.load_markets() # 取引所の通貨ペア情報を読み込む
            logging.info(f"TradingExecutor initialized successfully with {exchange_id}.")

        except Exception as e:
            logging.error(f"Failed to initialize exchange: {e}")

    def load_markets(self):
        """取引所の市場情報をロードし、ティッカーの対応表を作成する"""
        try:
            markets = self.exchange.load_markets()
            for ticker, market_info in markets.items():
                if 'baseId' in market_info:
                    # 'bitcoin' (CoinGecko ID) -> 'BTC/USDT' (取引所ティッカー) のようにマッピング
                    self.ticker_map[market_info['baseId'].lower()] = ticker
        except Exception as e:
            logging.error(f"Failed to load markets: {e}")

    def get_ticker_for_id(self, coingecko_id):
        """CoinGeckoのIDから取引所のティッカーを取得する"""
        return self.ticker_map.get(coingecko_id.lower())

    def open_long_position(self, token_id, series, trade_amount_usd=100.0):
        """
        新規にロングポジションを建てる。
        ATRを用いて動的な利確・損切りポイントを計算し、状態を記録する。
        """
        if self.state.has_position(token_id):
            logging.info(f"Already in position for {token_id}. Skipping new entry.")
            return
        
        ticker = self.get_ticker_for_id(token_id)
        if not ticker:
            logging.warning(f"Ticker for {token_id} not found on exchange. Cannot open position.")
            return
            
        # 1. 動的な利確(TP)・損切(SL)ポイントを計算
        try:
            series.ta.atr(append=True) # ATRを計算
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            
            # 損小利大の原則 (リスク:リワード比 1:2)
            stop_loss = current_price - (atr * 1.5)
            take_profit = current_price + (atr * 3.0)
            logging.info(f"Calculated exit points for {token_id}: TP=${take_profit:.4f}, SL=${stop_loss:.4f}")
        except Exception as e:
            logging.error(f"Could not calculate ATR for exit points: {e}")
            return

        # 2. 注文実行
        if not self.exchange:
            logging.warning(f"--- SIMULATION: Executing LONG for {token_id} at ${current_price:.4f} ---")
        else:
            try:
                logging.info(f"Executing market BUY order for {ticker} with cost {trade_amount_usd} USD.")
                # order = self.exchange.create_market_buy_order_with_cost(ticker, trade_amount_usd)
                # logging.info(f"BUY order successful. Order ID: {order['id']}")
            except Exception as e:
                logging.error(f"Failed to execute LONG for {ticker}: {e}")
                return

        # 3. ポジション情報を状態として記録
        position_details = {
            'ticker': ticker,
            'entry_price': current_price,
            'take_profit': take_profit,
            'stop_loss': stop_loss
        }
        self.state.set_position(token_id, True, position_details)

    def close_long_position(self, token_id, reason=""):
        """保有しているロングポジションを決済する"""
        if not self.state.has_position(token_id): return
        
        position_details = self.state.get_position_details(token_id)
        ticker = position_details.get('ticker')
        
        if not self.exchange:
            logging.warning(f"--- SIMULATION: Executing SELL for {token_id} due to {reason} ---")
        else:
            try:
                # 保有量を全量売却
                asset = ticker.split('/')[0]
                balance = self.exchange.fetch_balance()
                amount_to_sell = balance[asset]['free']
                
                if amount_to_sell > 0:
                    logging.info(f"Executing market SELL order for {amount_to_sell} {asset} due to {reason}.")
                    # order = self.exchange.create_market_sell_order(ticker, amount_to_sell)
                    # logging.info(f"SELL order successful. Order ID: {order['id']}")
                else:
                    logging.warning(f"No sellable assets for {ticker}. Closing position state.")
            except Exception as e:
                logging.error(f"Failed to execute SELL for {ticker}: {e}")
                # エラーが発生しても、ポジション情報はクローズする
        
        # ポジション情報をクリア
        self.state.set_position(token_id, False, None)

    def check_active_positions(self, data_aggregator):
        """保有中の全ポジションを監視し、TP/SLに達していたら決済する"""
        active_positions = self.state.get_all_positions()
        if not active_positions: return

        logging.info(f"Checking {len(active_positions)} active position(s)...")
        for token_id, details in active_positions.items():
            try:
                current_price = data_aggregator.get_latest_price(token_id)
                if not current_price: continue

                # 利確チェック
                if current_price >= details['take_profit']:
                    logging.info(f"✅ TAKE PROFIT triggered for {token_id} at ${current_price:.4f}")
                    self.close_long_position(token_id, reason="TAKE_PROFIT")
                
                # 損切りチェック
                elif current_price <= details['stop_loss']:
                    logging.info(f"🛑 STOP LOSS triggered for {token_id} at ${current_price:.4f}")
                    self.close_long_position(token_id, reason="STOP_LOSS")
            except Exception as e:
                logging.error(f"Could not check position for {token_id}: {e}")
