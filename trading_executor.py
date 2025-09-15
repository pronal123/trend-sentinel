import logging
import math
import os
from typing import Optional, Dict, Any

import ccxt
from state_manager import StateManager

PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"
BITGET_API_KEY = os.getenv("BITGET_API_KEY_FUTURES")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET_FUTURES")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE_FUTURES")


class TradingExecutor:
    """
    Bitget Futures 注文実行。
    PaperTrading時は StateManager に記録のみ。
    """

    def __init__(self, state_manager: StateManager):
        self.state = state_manager
        self.exchange = None
        try:
            self.exchange = ccxt.bitget({
                "apiKey": BITGET_API_KEY,
                "secret": BITGET_API_SECRET,
                "password": BITGET_API_PASSPHRASE,
                "enableRateLimit": True,
            })
            self.exchange.options["defaultType"] = "swap"
            logging.info("Initialized ccxt.bitget for futures.")
        except Exception as e:
            logging.warning("Could not initialize ccxt.bitget: %s", e)
            self.exchange = None

    def _market_symbol(self, symbol: str) -> str:
        return f"{symbol}/USDT:USDT"

    def _round_amount(self, symbol: str, amount: float) -> float:
        try:
            markets = self.exchange.load_markets()
            m = markets.get(symbol)
            if m:
                step = m.get("limits", {}).get("amount", {}).get("min")
                if step:
                    return math.floor(amount / step) * step
        except Exception:
            pass
        return round(amount, 6)

    def open_position(self, symbol: str, side: str, size_usd: float,
                      entry_price: float, tp: float, sl: float,
                      leverage: float = 3.0) -> Dict[str, Any]:
        symbol_pair = self._market_symbol(symbol)
        amount = self._round_amount(symbol_pair, size_usd / entry_price)
        logging.info(f"OPEN {side} {symbol} amt={amount} entry={entry_price} tp={tp} sl={sl}")

        if PAPER_TRADING or not self.exchange:
            self.state.open_position(symbol, side, entry_price, amount, tp, sl, leverage)
            return {"simulated": True}

        try:
            self.exchange.set_leverage(leverage, symbol_pair)
            if side == "long":
                order = self.exchange.create_market_buy_order(symbol_pair, amount)
            else:
                order = self.exchange.create_market_sell_order(symbol_pair, amount)
            executed_price = order.get("average") or entry_price
            self.state.open_position(symbol, side, executed_price, amount, tp, sl, leverage)
            return order
        except Exception as e:
            logging.exception("Failed to open position: %s", e)
            return {"error": str(e)}

    def close_position(self, symbol: str, portion: float = 1.0) -> Dict[str, Any]:
        if not self.state.has_position(symbol):
            return {"error": "no position"}
        pos = self.state.positions[symbol]
        side = pos["side"]
        amt = pos["amount"] * portion
        market_symbol = self._market_symbol(symbol)

        if PAPER_TRADING or not self.exchange:
            price = pos["entry_price"]
            rec = self.state.close_position(symbol, price, portion=portion, reason="PAPER")
            return {"simulated": True, "pnl": rec["pnl"]}

        try:
            if side == "long":
                order = self.exchange.create_market_sell_order(market_symbol, amt, {"reduceOnly": True})
            else:
                order = self.exchange.create_market_buy_order(market_symbol, amt, {"reduceOnly": True})
            price = order.get("average")
            rec = self.state.close_position(symbol, price, portion=portion, reason="LIVE")
            return {"order": order, "pnl": rec["pnl"]}
        except Exception as e:
            logging.exception("Failed to close position: %s", e)
            return {"error": str(e)}
