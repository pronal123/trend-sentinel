import logging
import ccxt
from config import EXCHANGE_ID, EXCHANGE_API_KEY, EXCHANGE_SECRET_KEY, EXCHANGE_API_PASSPHRASE, PAPER_TRADING_ENABLED

class TradingExecutor:
    def __init__(self, state):
        self.state = state
        self.exchange = None
        try:
            cls = getattr(ccxt, EXCHANGE_ID)
            cfg = {'apiKey': EXCHANGE_API_KEY, 'secret': EXCHANGE_SECRET_KEY}
            if EXCHANGE_API_PASSPHRASE:
                cfg['password'] = EXCHANGE_API_PASSPHRASE
            self.exchange = cls(cfg)
            self.exchange.load_markets()
            logging.info(f"TradingExecutor initialized on {EXCHANGE_ID}")
        except Exception as e:
            logging.error("Exchange init fail: %s", e)
            self.exchange = None

    def calculate_position_size_usd(self, score, base_usd=50, max_usd=500):
        # example mapping
        if score < 50: return 0
        return min(max_usd, base_usd + (score-50)/50 * (max_usd-base_usd))

    def open_position(self, side, symbol, position_size_usd, notifier=None):
        """Place market order. side = 'LONG' or 'SHORT'"""
        if PAPER_TRADING_ENABLED or not self.exchange:
            logging.info(f"[PAPER] Open {side} {symbol} size ${position_size_usd}")
            # simulate
            self.state.set_position(symbol, {"side": side, "entry_time": None, "position_size_usd": position_size_usd})
            return True
        try:
            # For spot: buy = market buy, sell = market sell
            # For futures: API params differ; real implementation required per exchange
            price = self.exchange.fetch_ticker(symbol).get('last')
            amount = position_size_usd / price if price else 0
            if side == 'LONG':
                order = self.exchange.create_market_buy_order(symbol, amount)
            else:
                order = self.exchange.create_market_sell_order(symbol, amount)
            logging.info("Order placed %s", order)
            self.state.set_position(symbol, {"side": side, "entry_price": price, "amt": amount})
            return True
        except Exception as e:
            logging.error("Order failed: %s", e)
            if notifier:
                notifier.send(f"Order failed for {symbol}: {e}")
            return False

    def close_position(self, symbol, notifier=None):
        # simplified: close and record PnL if possible; implement properly per exchange
        if PAPER_TRADING_ENABLED or not self.exchange:
            logging.info(f"[PAPER] Close {symbol}")
            self.state.remove_position(symbol)
            return True
        try:
            details = self.state.get_positions().get(symbol)
            if not details: return False
            # implement exchange-specific close
            self.state.remove_position(symbol)
            return True
        except Exception as e:
            logging.error("Close failed: %s", e)
            return False
