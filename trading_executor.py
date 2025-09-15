import ccxt
import os

class TradingExecutor:
    def __init__(self):
        self.exchange = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY"),
            "secret": os.getenv("BITGET_API_SECRET"),
            "password": os.getenv("BITGET_API_PASSPHRASE"),
            "enableRateLimit": True,
        })
        self.market_type = "swap"  # USDT無期限先物

    def open_position(self, symbol, side, size):
        order_side = "buy" if side == "long" else "sell"
        return self.exchange.create_market_order(
            symbol=f"{symbol}/USDT:{self.market_type}",
            side=order_side,
            amount=size
        )

    def close_position(self, symbol, side, size):
        order_side = "sell" if side == "long" else "buy"
        return self.exchange.create_market_order(
            symbol=f"{symbol}/USDT:{self.market_type}",
            side=order_side,
            amount=size,
            params={"reduceOnly": True}
        )
