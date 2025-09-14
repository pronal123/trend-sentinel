import os
import ccxt
import logging

class TradingExecutor:
    def __init__(self, state_manager):
        self.state_manager = state_manager

        # Spot
        self.enable_spot = os.getenv("ENABLE_SPOT", "false").lower() == "true"
        if self.enable_spot:
            self.spot_client = ccxt.bitget({
                "apiKey": os.getenv("BITGET_SPOT_API_KEY"),
                "secret": os.getenv("BITGET_SPOT_API_SECRET"),
                "password": os.getenv("BITGET_SPOT_API_PASSPHRASE"),
                "options": {"defaultType": "spot"},
            })
            logging.info("✅ Spot client initialized")
        else:
            self.spot_client = None
            logging.info("⚠️ Spot client disabled")

        # Futures
        self.enable_futures = os.getenv("ENABLE_FUTURES", "false").lower() == "true"
        if self.enable_futures:
            self.futures_client = ccxt.bitget({
                "apiKey": os.getenv("BITGET_FUTURES_API_KEY"),
                "secret": os.getenv("BITGET_FUTURES_API_SECRET"),
                "password": os.getenv("BITGET_FUTURES_API_PASSPHRASE"),
                "options": {"defaultType": "swap"},
            })
            logging.info("✅ Futures client initialized")
        else:
            self.futures_client = None
            logging.info("⚠️ Futures client disabled")

    def open_position(self, side, symbol, series, score, notifier, analysis_comment,
                      position_size_usd=100, market_type="spot"):

        if market_type == "spot":
            if not self.enable_spot or not self.spot_client:
                logging.warning("Spot trading disabled")
                return None
            client = self.spot_client

        elif market_type == "futures":
            if not self.enable_futures or not self.futures_client:
                logging.warning("Futures trading disabled")
                return None
            client = self.futures_client

        else:
            logging.error(f"Unknown market_type={market_type}")
            return None

        # --- 発注処理例 ---
        try:
            if side == "LONG":
                order = client.create_market_buy_order(symbol, 0.001)  # ⚠️ size計算は別途
            elif side == "SHORT":
                order = client.create_market_sell_order(symbol, 0.001)
            else:
                logging.error(f"Invalid side={side}")
                return None

            logging.info(f"✅ Order executed {market_type} {side}: {order}")
            return order

        except Exception as e:
            logging.error(f"注文失敗 ({market_type} {side}): {e}")
            return None
