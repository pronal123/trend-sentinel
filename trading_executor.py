# trading_executor.py
import logging
import ccxt
import pandas_ta as ta
import config

class TradingExecutor:
    """
    取引の実行、リスク管理、ポジション監視を担うクラス。
    config.pyの設定に基づき、現物・先物取引を自動で切り替える。
    """
    def __init__(self, state_manager):
        self.state = state_manager
        self.exchange = None
        self.market_type = config.EXCHANGE_MARKET_TYPE
        
        if config.PAPER_TRADING_ENABLED:
            logging.warning("Paper Trading is ENABLED. No real orders will be placed.")
        
        if not all([config.EXCHANGE_ID, config.EXCHANGE_API_KEY, config.EXCHANGE_SECRET_KEY]):
            logging.error("API credentials are not fully set in config/environment.")
            return

        try:
            exchange_class = getattr(ccxt, config.EXCHANGE_ID)
            api_config = {
                'apiKey': config.EXCHANGE_API_KEY,
                'secret': config.EXCHANGE_SECRET_KEY,
            }
            if config.EXCHANGE_API_PASSPHRASE:
                api_config['password'] = config.EXCHANGE_API_PASSPHRASE
            
            self.exchange = exchange_class(api_config)
            self.exchange.options['defaultType'] = self.market_type
            self.exchange.load_markets()
            logging.info(f"TradingExecutor initialized for '{config.EXCHANGE_ID}' in '{self.market_type}' mode.")
        except Exception as e:
            logging.error(f"FATAL: Failed to initialize exchange: {e}")

    def get_account_balance_usd(self):
        """取引所の口座残高（USDT）を取得する"""
        if not self.exchange or config.PAPER_TRADING_ENABLED:
            logging.info("Returning dummy balance for paper trading or uninitialized exchange.")
            return 10000.0
        try:
            balance = self.exchange.fetch_balance()
            return balance.get('USDT', {}).get('free', 0.0)
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}")
            return 0.0

    def get_ticker_for_id(self, coingecko_id):
        """CoinGecko IDから取引所のティッカー形式に変換する"""
        symbol_upper = coingecko_id.split('-')[0].upper()
        # 先物の場合、':USDT'などのサフィックスが必要な取引所がある
        return f"{symbol_upper}/USDT:USDT" if self.market_type == 'swap' else f"{symbol_upper}/USDT"

    def calculate_position_size(self, score, base_size_usd, max_size_usd):
        """スコア(0-100)に基づいてポジションサイズ(USD)を動的に計算する"""
        entry_threshold = config.ENTRY_SCORE_THRESHOLD_TRENDING # 仮。実際はmainから渡されるべき
        if score < entry_threshold:
            return 0.0
        
        # スコアが閾値で基本サイズ、100点で最大サイズになるよう線形に計算
        size = base_size_usd + ((score - entry_threshold) / (100 - entry_threshold)) * (max_size_usd - base_size_usd)
        return round(size, 2)

    def open_position(self, signal_type, token_id, series, score, notifier=None, analysis_comment="", position_size_usd=0):
        """分析結果に基づき、新規ポジションを建てる"""
        if self.state.has_position(token_id):
            logging.warning(f"Position for {token_id} already exists. Skipping open.")
            return

        if signal_type == 'SHORT' and not config.ENABLE_FUTURES_TRADING:
            logging.warning("SHORT signal received, but futures trading is disabled in config. Skipping.")
            return

        if position_size_usd <= 0:
            logging.info(f"Position size is zero for {token_id} (Score: {score:.1f}). Not opening position.")
            return

        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['close'].iloc[-1]
            position_size_asset = position_size_usd / current_price
            
            if signal_type == 'LONG':
                stop_loss = current_price - (atr * config.ATR_STOP_LOSS_MULTIPLIER)
                take_profit = current_price + (atr * config.ATR_TAKE_PROFIT_MULTIPLIER)
            else: # SHORT
                stop_loss = current_price + (atr * config.ATR_STOP_LOSS_MULTIPLIER)
                take_profit = current_price - (atr * config.ATR_TAKE_PROFIT_MULTIPLIER)
        except Exception as e:
            logging.error(f"Failed to calculate SL/TP for {token_id}: {e}")
            return

        ticker = self.get_ticker_for_id(token_id)
        try:
            logging.info(f"Attempting to open {signal_type} position for {ticker} | Size: ${position_size_usd:.2f} | SL: {stop_loss:.4f} | TP: {take_profit:.4f}")
            
            if config.PAPER_TRADING_ENABLED:
                logging.warning(f"--- SIMULATION: Executed {signal_type} for {token_id} ---")
            elif self.exchange:
                if signal_type == 'LONG':
                    order = self.exchange.create_market_buy_order(ticker, position_size_asset)
                elif signal_type == 'SHORT':
                    order = self.exchange.create_market_sell_order(ticker, position_size_asset)
                logging.info(f"SUCCESS: {signal_type} order placed for {ticker}. Order ID: {order['id']}")
            
            position_details = {
                'ticker': ticker, 'side': signal_type.lower(), 'entry_price': current_price,
                'take_profit': take_profit, 'stop_loss': stop_loss, 'position_size': position_size_asset
            }
            self.state.set_position(token_id, True, position_details)
            if notifier:
                notifier.send_new_position_notification(position_details, score, analysis_comment)

        except Exception as e:
            logging.error(f"Failed to open {signal_type} position for {ticker}: {e}")
            if notifier: notifier.send_error_notification(f"注文失敗 ({ticker}): {e}")

    def close_position(self, token_id, close_price, reason, notifier=None):
        """保有中のポジションを決済する"""
        if not self.state.has_position(token_id): return
        
        details = self.state.get_position_details(token_id)
        ticker, position_size, side = details['ticker'], details['position_size'], details['side']
        
        try:
            logging.info(f"Attempting to close {side} position for {ticker} due to {reason}.")

            if config.PAPER_TRADING_ENABLED:
                logging.warning(f"--- SIMULATION: Closed {side} for {token_id} ---")
            elif self.exchange:
                if side == 'long':
                    self.exchange.create_market_sell_order(ticker, position_size)
                elif side == 'short':
                    # 先物ショートポジションの決済は買い注文
                    self.exchange.create_market_buy_order(ticker, position_size, {'reduceOnly': True})

            # 利益/損失を計算
            pnl = (close_price - details['entry_price']) * position_size if side == 'long' else (details['entry_price'] - close_price) * position_size
            result = 'win' if pnl > 0 else 'loss'
            
            self.state.record_trade_result(token_id, result)
            self.state.set_position(token_id, False, None)
            if notifier:
                notifier.send_close_position_notification(ticker, reason, result, pnl)
        except Exception as e:
            logging.error(f"Failed to close position for {ticker}: {e}")

    def check_active_positions(self, data_aggregator, notifier=None):
        """保有中の全ポジションを監視し、利食い/損切りラインに達していないか確認する"""
        active_positions = self.state.get_all_active_positions()
        if not active_positions: return

        logging.info(f"Checking {len(active_positions)} active position(s)...")
        for token_id, details in active_positions.items():
            try:
                current_price = data_aggregator.get_latest_price(token_id)
                if not current_price: continue

                side = details['side']
                if side == 'long':
                    if current_price >= details['take_profit']:
                        self.close_position(token_id, current_price, "TAKE PROFIT", notifier)
                    elif current_price <= details['stop_loss']:
                        self.close_position(token_id, current_price, "STOP LOSS", notifier)
                elif side == 'short':
                    if current_price <= details['take_profit']:
                        self.close_position(token_id, current_price, "TAKE PROFIT", notifier)
                    elif current_price >= details['stop_loss']:
                        self.close_position(token_id, current_price, "STOP LOSS", notifier)
            except Exception as e:
                logging.error(f"Could not check position for {token_id}: {e}")
