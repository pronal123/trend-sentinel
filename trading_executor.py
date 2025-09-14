# trading_executor.py
import os
import logging
import ccxt
import pandas_ta as ta

class TradingExecutor:
    def __init__(self, state_manager):
        self.state = state_manager
        self.exchange = None
        
        # --- 環境変数から設定を読み込み ---
        exchange_id = os.environ.get('EXCHANGE_ID')
        api_key = os.environ.get('EXCHANGE_API_KEY')
        api_secret = os.environ.get('EXCHANGE_SECRET_KEY')
        api_passphrase = os.environ.get('EXCHANGE_API_PASSPHRASE')
        self.market_type = os.environ.get('EXCHANGE_MARKET_TYPE', 'spot') # spot (現物) or swap (先物)

        if not all([exchange_id, api_key, api_secret]):
            logging.warning("API credentials not fully set. Running in SIMULATION mode.")
            return

        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {'apiKey': api_key, 'secret': api_secret}
            if api_passphrase: config['password'] = api_passphrase
            
            self.exchange = exchange_class(config)
            self.exchange.options['defaultType'] = self.market_type
            self.exchange.load_markets()
            logging.info(f"TradingExecutor initialized for '{exchange_id}' in '{self.market_type}' mode.")
        except Exception as e:
            logging.error(f"Failed to initialize exchange: {e}")

    def get_ticker_for_id(self, coingecko_id):
        # CoinGecko ID ('bitcoin') から取引所ティッカー ('BTC/USDT') を検索（簡易版）
        symbol_upper = coingecko_id.split('-')[0].upper()
        return f"{symbol_upper}/USDT:USDT" if self.market_type == 'swap' else f"{symbol_upper}/USDT"

    def calculate_position_size(self, base_size_usd, max_size_usd, score):
        """スコア(0-100)に基づいてポジションサイズ(USD)を計算"""
        if score < 60: # スコアが60未満の場合は取引しない
            return 0
        size = base_size_usd + ((score - 60) / 40) * (max_size_usd - base_size_usd)
        return size

    def open_position(self, signal_type, token_id, series, score, notifier=None, analysis_comment=""):
        if self.state.has_position(token_id):
            logging.warning(f"Position for {token_id} already exists. Skipping open.")
            return

        # 1. ポジションサイズを計算
        # TODO: BOTの設定に合わせて基本サイズと最大サイズを調整
        position_size_usd = self.calculate_position_size(base_size_usd=50.0, max_size_usd=200.0, score=score)
        if position_size_usd <= 0:
            logging.info(f"Low score for {token_id} ({score:.1f}). Not opening position.")
            return

        # 2. リスク管理（利食い・損切り）ラインをATRで計算
        try:
            series.ta.atr(append=True)
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['close'].iloc[-1]
            position_size_asset = position_size_usd / current_price
            
            if signal_type == 'LONG':
                stop_loss = current_price - (atr * 1.5)
                take_profit = current_price + (atr * 3.0)
            elif signal_type == 'SHORT':
                if self.market_type != 'swap':
                    logging.warning("SHORT positions are only supported in 'swap' (futures) market type.")
                    return
                stop_loss = current_price + (atr * 1.5)
                take_profit = current_price - (atr * 3.0)
            else:
                return

        except Exception as e:
            logging.error(f"Failed to calculate SL/TP for {token_id}: {e}")
            return

        # 3. 注文を実行
        ticker = self.get_ticker_for_id(token_id)
        try:
            logging.info(f"Attempting to open {signal_type} position for {ticker} | Size: ${position_size_usd:.2f}")
            
            # --- 実行時は以下のコメントを外す ---
            # if signal_type == 'LONG':
            #     order = self.exchange.create_market_buy_order(ticker, position_size_asset)
            # elif signal_type == 'SHORT':
            #     order = self.exchange.create_market_sell_order(ticker, position_size_asset)
            
            logging.warning(f"--- SIMULATION: Executed {signal_type} for {token_id} ---")

            # 4. ポジション情報を記録
            position_details = {
                'ticker': ticker, 'side': signal_type.lower(), 'entry_price': current_price,
                'take_profit': take_profit, 'stop_loss': stop_loss, 'position_size': position_size_asset
            }
            self.state.set_position(token_id, True, position_details)

            # 5. 通知
            if notifier:
                notifier.send_new_position_notification(position_details, score, analysis_comment)

        except Exception as e:
            logging.error(f"Failed to open {signal_type} position for {ticker}: {e}")
            if notifier: notifier.send_error_notification(f"注文失敗 ({ticker}): {e}")

    def close_position(self, token_id, close_price, reason, notifier=None):
        if not self.state.has_position(token_id): return
        
        details = self.state.get_position_details(token_id)
        ticker = details['ticker']
        position_size = details['position_size']
        side = details['side']
        
        try:
            logging.info(f"Attempting to close {side} position for {ticker} at {close_price:.4f} due to {reason}.")

            # --- 実行時は以下のコメントを外す ---
            # if side == 'long':
            #     order = self.exchange.create_market_sell_order(ticker, position_size)
            # elif side == 'short':
            #     order = self.exchange.create_market_buy_order(ticker, position_size, {'reduceOnly': True})
            
            logging.warning(f"--- SIMULATION: Closed {side} for {token_id} ---")

            # 利益/損失を計算
            if side == 'long':
                pnl = (close_price - details['entry_price']) * position_size
            else: # short
                pnl = (details['entry_price'] - close_price) * position_size
            result = 'win' if pnl > 0 else 'loss'
            
            self.state.record_trade_result(token_id, result)
            self.state.set_position(token_id, False, None)

            if notifier:
                notifier.send_close_position_notification(ticker, reason, result, pnl)
        except Exception as e:
            logging.error(f"Failed to close position for {ticker}: {e}")

    def check_active_positions(self, data_aggregator, notifier=None):
        active_positions = self.state.get_all_active_positions()
        if not active_positions: return

        logging.info(f"Checking {len(active_positions)} active position(s)...")
        for token_id, details in active_positions.items():
            try:
                # TODO: data_aggregatorに最新価格を取得する機能を追加
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

