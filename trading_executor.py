import os
import logging
import ccxt
from typing import Tuple

logger = logging.getLogger(__name__)

class TradingExecutor:
    """
    Bitget Futures (USDT perpetual) trading via ccxt.
    - Paper trading if PAPER_TRADING=1
    - create_order / close order for market execution
    """

    def __init__(self):
        self.api_key = os.getenv("BITGET_FUTURES_API_KEY") or os.getenv("BITGET_API_KEY")
        self.api_secret = os.getenv("BITGET_FUTURES_API_SECRET") or os.getenv("BITGET_API_SECRET")
        self.api_pass = os.getenv("BITGET_FUTURES_API_PASSPHRASE") or os.getenv("BITGET_API_PASSPHRASE")
        self.paper = os.getenv("PAPER_TRADING", "1") != "0"

        if not self.paper:
            try:
                self.ex = ccxt.bitget({
                    "apiKey": self.api_key,
                    "secret": self.api_secret,
                    "password": self.api_pass,
                    "enableRateLimit": True,
                })
                # ensure futures mode for perpetual: ccxt unified markets may differ
                # Some exchanges need self.ex.options['defaultType']='future'
                self.ex.options = getattr(self.ex, "options", {})
                self.ex.options['defaultType'] = 'future'
                logger.info("Initialized ccxt.bitget for futures.")
            except Exception as e:
                logger.exception("Failed to init ccxt.bitget: %s", e)
                self.ex = None
        else:
            logger.warning("PAPER_TRADING enabled: orders will not be sent.")
            self.ex = None

    def _symbol_for_ccxt(self, symbol: str) -> str:
        """Return ccxt-like symbol for USDT perpetual. e.g. 'BTC/USDT:USDT' or 'BTC/USDT' depending on exchange."""
        # ccxt.bitget often uses 'BTC/USDT:USDT' for unified. We'll try that.
        return f"{symbol}/USDT:USDT"

    def place_futures_market_order(self, symbol: str, side: str, amount: float, reduce_only: bool=False) -> dict:
        """
        Place market order on futures.
        side: 'long' or 'short'. For create_order, side param is 'buy' or 'sell'.
        amount: in base asset units (e.g. BTC)
        reduce_only: if True, closes existing position
        """
        order_side = "buy" if side.lower() == "long" else "sell"
        ccxt_symbol = self._symbol_for_ccxt(symbol)
        logger.info("Placing futures market order %s %s %s (reduceOnly=%s)", ccxt_symbol, order_side, amount, reduce_only)
        if self.paper or not self.ex:
            # simulate response
            return {
                "info": {"simulated": True},
                "id": f"SIM-{symbol}-{int(time.time())}",
                "status": "closed",
                "side": order_side,
                "filled": amount
            }
        try:
            params = {}
            if reduce_only:
                params['reduceOnly'] = True
            # create market order
            order = self.ex.create_market_order(ccxt_symbol, order_side, amount, params=params)
            return order
        except Exception as e:
            logger.exception("Order placement failed: %s", e)
            return {"error": str(e)}

    def close_futures_position(self, symbol: str, side: str, amount: float) -> dict:
        # Closing is opposite side with reduceOnly True
        opposite = "short" if side.lower() == "long" else "long"
        return self.place_futures_market_order(symbol, opposite, amount, reduce_only=True)
