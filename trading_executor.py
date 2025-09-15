# trading_executor.py
import logging
import math
import os
from typing import Optional, Dict, Any, List

import ccxt

PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"
BITGET_API_KEY = os.getenv("BITGET_API_KEY_FUTURES", "")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET_FUTURES", "")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE_FUTURES", "")

class TradingExecutor:
    def __init__(self, state_manager):
        self.state = state_manager
        self.exchange = None
        try:
            cfg = {
                "apiKey": BITGET_API_KEY,
                "secret": BITGET_API_SECRET,
                "password": BITGET_API_PASSPHRASE,
                "enableRateLimit": True,
            }
            self.exchange = ccxt.bitget(cfg)
            try:
                self.exchange.options["defaultType"] = "swap"
            except Exception:
                pass
            logging.info("Initialized ccxt.bitget for futures.")
        except Exception as e:
            logging.warning("Could not initialize ccxt.bitget: %s", e)
            self.exchange = None

    def _market_symbol(self, symbol: str) -> str:
        # ccxt bitget for swap uses 'BTC/USDT:USDT'
        base = symbol.replace("/", "").upper()
        if "/" in symbol:
            return symbol  # already like 'ETH/USDT'
        return f"{symbol}/USDT:USDT"

    def _round_amount(self, market_symbol: str, amount: float) -> float:
        try:
            self.exchange.load_markets()
            m = self.exchange.market(market_symbol)
            precision = m.get("precision", {}).get("amount", None)
            if precision is not None:
                fmt = "{:." + str(int(precision)) + "f}"
                return float(fmt.format(amount))
        except Exception:
            pass
        return float(round(amount, 6))

    def set_leverage(self, market_symbol: str, leverage: int):
        # ccxt bitget: set_leverage might not exist; this is best-effort placeholder.
        try:
            if hasattr(self.exchange, "set_leverage"):
                self.exchange.set_leverage(leverage, market_symbol)
        except Exception as e:
            logging.debug("set_leverage failed: %s", e)

    def open_position(self, symbol: str, side: str, size_usd: float, entry_price: float,
                      take_profit: float, stop_loss: float, leverage: int = 3,
                      partial_steps: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        Open futures position. size_usd = notional USDT. Convert to amount via price.
        partial_steps e.g. [0.5,0.25,0.25]
        """
        market_sym = self._market_symbol(symbol)
        amount = size_usd / max(1e-9, float(entry_price))
        amount = self._round_amount(market_sym, amount)
        logging.info("Open position request: %s %s amount=%s @%s (TP=%s SL=%s) lev=%s",
                     symbol, side, amount, entry_price, take_profit, stop_loss, leverage)

        if PAPER_TRADING or not self.exchange:
            self.state.open_position(symbol, side, entry_price, amount, take_profit, stop_loss, leverage)
            return {"simulated": True, "symbol": symbol, "side": side, "amount": amount}

        try:
            # set leverage
            self.set_leverage(market_sym, leverage)
            if side.lower() == "long":
                order = self.exchange.create_market_buy_order(market_sym, amount)
            else:
                order = self.exchange.create_market_sell_order(market_sym, amount)
            executed_price = order.get("average") or order.get("price") or entry_price
            self.state.open_position(symbol, side, executed_price, amount, take_profit, stop_loss, leverage)
            return {"order": order}
        except Exception as e:
            logging.exception("open_position live failed: %s", e)
            return {"error": str(e)}

    def close_position(self, symbol: str, portion: float = 1.0) -> Dict[str, Any]:
        """
        Close portion of a position. portion in (0,1].
        """
        pos = self.state.get_position(symbol)
        if not pos:
            raise KeyError("No position for " + symbol)
        side = pos["side"]
        total_amount = float(pos["amount"])
        close_amount = float(total_amount) * float(portion)
        market_sym = self._market_symbol(symbol)

        if PAPER_TRADING or not self.exchange:
            # simulate exit at current ticker price if possible
            price = None
            try:
                if self.exchange:
                    t = self.exchange.fetch_ticker(market_sym)
                    price = t.get("last") or t.get("close")
            except Exception:
                price = None
            if price is None:
                price = pos["entry_price"]
            rec = self.state.close_position(symbol, price, reason=f"PAPER_CLOSE_{portion}")
            return {"simulated": True, "pnl": rec["pnl"], "trade": rec}
        try:
            if side == "long":
                order = self.exchange.create_market_sell_order(market_sym, close_amount, {"reduceOnly": True})
            else:
                order = self.exchange.create_market_buy_order(market_sym, close_amount, {"reduceOnly": True})
            executed_price = order.get("average") or order.get("price")
            rec = self.state.close_position(symbol, executed_price, reason="LIVE_CLOSE")
            return {"order": order, "pnl": rec["pnl"], "trade": rec}
        except Exception as e:
            logging.exception("close_position live failed: %s", e)
            return {"error": str(e)}
