# trading_executor.py
import logging
import ccxt
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TradingExecutor:
    """
    Futures (USDT perpetual) 注文を送信するラッパー。
    - paper=True のときは実注文を送らずログのみ（state updateは呼び出し元で行う）
    - symbol は "BTC" 等のシンボル（内部で ccxt 用に 'BTC/USDT:USDT' に変換）
    """

    def __init__(self, api_key: Optional[str], api_secret: Optional[str], api_passphrase: Optional[str] = None,
                 exchange_id: str = "bitget", paper: bool = True):
        self.paper = paper
        self.exchange = None
        if self.paper:
            logger.info("TradingExecutor initialized in PAPER_TRADING mode.")
            return

        if not all([api_key, api_secret]):
            logger.error("API keys not provided — falling back to paper trading mode.")
            self.paper = True
            return

        try:
            exc_cls = getattr(ccxt, exchange_id)
            cfg = {
                "apiKey": api_key,
                "secret": api_secret
            }
            # bitget uses passphrase for some markets; include if provided
            if api_passphrase:
                cfg["password"] = api_passphrase
            self.exchange = exc_cls(cfg)
            # ensure futures/perpetual mode
            try:
                self.exchange.options['defaultType'] = 'swap'
            except Exception:
                pass
            self.exchange.load_markets()
            logger.info("TradingExecutor connected to exchange %s", exchange_id)
        except Exception as e:
            logger.exception("Failed to init exchange client: %s. Switching to paper mode.", e)
            self.exchange = None
            self.paper = True

    def _to_ccxt_symbol(self, symbol: str) -> str:
        # CCXT bitget perpetual format often is "BTC/USDT:USDT"
        base = symbol.upper()
        return f"{base}/USDT:USDT"

    def open_futures_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        Open market futures position.
        side: 'long' or 'short'
        amount: asset units (contract quantity). NOTE: depending on exchange, amount meaning vary - test carefully.
        Returns order dict (or simulated result).
        """
        logger.info("open_futures_position %s %s amount=%s (paper=%s)", symbol, side, amount, self.paper)
        if self.paper or not self.exchange:
            # simulate order result
            return {"status": "simulated", "symbol": symbol, "side": side, "amount": amount, "price": None}
        try:
            ccxt_symbol = self._to_ccxt_symbol(symbol)
            if side.lower() == "long":
                order = self.exchange.create_order(ccxt_symbol, 'market', 'buy', amount, None, {"reduceOnly": False})
            else:
                order = self.exchange.create_order(ccxt_symbol, 'market', 'sell', amount, None, {"reduceOnly": False})
            logger.info("Order placed: %s", order)
            return order
        except Exception as e:
            logger.exception("open order failed: %s", e)
            return {"error": str(e)}

    def close_futures_position(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        Close (partial or full) position by placing opposite market order with reduceOnly flag.
        side: current side ('long' or 'short') -> we send opposite order
        amount: quantity to close
        """
        logger.info("close_futures_position %s side=%s amount=%s (paper=%s)", symbol, side, amount, self.paper)
        if amount <= 0:
            return {"status": "nothing"}
        if self.paper or not self.exchange:
            return {"status": "simulated", "symbol": symbol, "side": side, "amount": amount}
        try:
            ccxt_symbol = self._to_ccxt_symbol(symbol)
            # place opposite side order with reduceOnly True
            if side.lower() == "long":
                # closing long = sell
                order = self.exchange.create_order(ccxt_symbol, 'market', 'sell', amount, None, {"reduceOnly": True})
            else:
                # closing short = buy
                order = self.exchange.create_order(ccxt_symbol, 'market', 'buy', amount, None, {"reduceOnly": True})
            logger.info("Close order placed: %s", order)
            return order
        except Exception as e:
            logger.exception("close order failed: %s", e)
            return {"error": str(e)}
