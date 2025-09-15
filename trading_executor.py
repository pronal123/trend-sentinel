import ccxt
import os
import logging
import math

class TradingExecutor:
    def __init__(self):
        self.exchange = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY"),
            "secret": os.getenv("BITGET_API_SECRET"),
            "password": os.getenv("BITGET_API_PASSWORD"),
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        self.paper = os.getenv("PAPER_TRADING", "True").lower() == "true"

    def round_quantity(self, symbol, qty):
        markets = self.exchange.load_markets()
        market = markets.get(symbol)
        if not market:
            return qty
        step = market["limits"]["amount"]["min"] or market["precision"]["amount"]
        return math.floor(qty / step) * step

    def set_leverage(self, symbol, leverage=5):
        try:
            self.exchange.set_leverage(leverage, symbol)
            logging.info(f"Leverage {leverage} set for {symbol}")
        except Exception as e:
            logging.warning(f"Failed to set leverage: {e}")

    def open_position(self, symbol, side, usd_size, price):
        qty = usd_size / price
        qty = self.round_quantity(symbol, qty)
        self.set_leverage(symbol, 5)

        if self.paper:
            logging.info(f"[PAPER] Open {side} {qty} {symbol} at {price}")
            return {"symbol": symbol, "side": side, "size": qty, "price": price}

        try:
            params = {"type": "market"}
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side="buy" if side == "long" else "sell",
                amount=qty,
                params=params,
            )
            logging.info(f"Order executed: {order}")
            return order
        except Exception as e:
            logging.error(f"Open position failed: {e}")
            return None

    def close_position(self, symbol, side, size):
        if self.paper:
            logging.info(f"[PAPER] Close {side} {size} {symbol}")
            return True
        try:
            params = {"reduceOnly": True}
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side="sell" if side == "long" else "buy",
                amount=size,
                params=params,
            )
            logging.info(f"Close order: {order}")
            return order
        except Exception as e:
            logging.error(f"Close position failed: {e}")
            return None
