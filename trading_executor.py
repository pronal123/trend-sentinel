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
        self.exchange = None  # 先にNoneで初期化
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
            config = {
                'apiKey': api_key,
                'secret': api_secret,
            }
            if api_passphrase:
                config['password'] = api_passphrase  # Bitgetなどのパスフレーズに対応

            # ccxtのインスタンスを'self.exchange'としてクラスの属性に保存
            self.exchange = exchange_class(config)
            
            self.load_markets()  # 取引所の通貨ペア情報を読み込む
            logging.info(f"TradingExecutor initialized successfully with {exchange_id}.")

        except Exception as e:
            logging.error(f"Failed to initialize exchange: {e}")
            self.exchange = None # エラー時もNoneをセット

    def load_markets(self):
        """取引所の市場情報をロードし、ティッカーの対応表を作成する"""
        if not self.exchange: return
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

    def get_account_balance_usd(self):
        """取引所の総資産（USD換算）を取得する"""
        if not self.exchange: return 10000.0  # シミュレーション用のダミー残高
        try:
            balance = self.exchange.fetch_balance()
            # ここでは簡略化のためUSD残高のみを返す (実際の運用では全資産を評価する必要がある)
            return balance.get('USD', {}).get('total', 10000.0)
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}")
            return None

    def open_long_position(self, token_id, series, trade_amount_usd, reason="", notifier=None, win_rate=0.0):
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
            series.ta.atr(append=True)  # ATRを計算
            atr = series['ATRr_14'].iloc[-1]
            current_price = series['Close'].iloc[-1]
            
            # 損小利大の原則 (リスク:リワード比 1:2)
            stop_loss = current_price - (atr * 1.5)
            take_profit = current_price + (atr * 3.0)
            logging.info(f"Calculated exit points for {token_id}: TP=${take_profit:,.4f}, SL=${stop_loss:,.4f}")
        except Exception as e:
            logging.error(f"Could not calculate exit points: {e}")
            return

        # 2. 残高とポジションサイズを取得
        current_balance = self.get_account_balance_usd()
        if not current_balance: return
        
        position_size = trade_amount_usd / current_price
        asset = ticker.split('/')[0]

        # 3. 注文実行 (シミュレーション)
        logging.warning(f"--- SIMULATION: Executing LONG for {token_id} at ${current_price:,.4f} ---")
        
        # 4. ポジション情報を状態として記録
        position_details = {
            'ticker': ticker,
            'entry_price': current_price,
            'take_profit': take_profit,
            'stop_loss': stop_loss,
            'position_size': position_size,
            'trade_amount_usd': trade_amount_usd
        }
        self.state.set_position(token_id, True, position_details)

        # 5. 詳細なTelegram通知を送信
        if notifier:
            notification_data = {
                'ticker': ticker, 'asset': asset, 'entry_price': current_price,
                'take_profit': take_profit, 'stop_loss': stop_loss,
                'current_balance': current_balance, 'position_size': position_size,
                'trade_amount_usd': trade_amount_usd, 'win_rate': win_rate, 'reason': reason
            }
            notifier.send_new_position_notification(notification_data)

    def close_long_position(self, token_id, close_price, reason=""):
        """保有しているロングポジションを決済する"""
        if not self.state.has_position(token_id): return
        
        details = self.state.get_position_details(token_id)
        
        # 1. 勝敗を判断して記録
        result = 'win' if close_price > details['entry_price'] else 'loss'
        self.state.record_trade_result(token_id, result)
        
        # 2. 注文実行 (シミュレーション)
        logging.warning(f"--- SIMULATION: Executing SELL for {token_id} at ${close_price:,.4f} due to {reason} ---")
        
        # 3. ポジション情報をクリア
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
                    logging.info(f"✅ TAKE PROFIT triggered for {token_id} at ${current_price:,.4f}")
                    self.close_long_position(token_id, current_price, reason="TAKE_PROFIT")
                
                # 損切りチェック
                elif current_price <= details['stop_loss']:
                    logging.info(f"🛑 STOP LOSS triggered for {token_id} at ${current_price:,.4f}")
                    self.close_long_position(token_id, current_price, reason="STOP_LOSS")
            except Exception as e:
                logging.error(f"Could not check position for {token_id}: {e}")
