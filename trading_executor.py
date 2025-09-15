# trading_executor.py
import logging
import math
import os
from typing import Optional, Dict, Any

import ccxt

# PAPER_TRADING フラグは環境変数で管理
PAPER_TRADING = os.getenv("PAPER_TRADING", "1") != "0"
BITGET_API_KEY = os.getenv("BITGET_API_KEY_FUTURES")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET_FUTURES")
BITGET_API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE_FUTURES")

class TradingExecutor:
    """
    Bitget Futures を使う注文実行クラス（ccxt ベース）。
    PaperTrading の場合は実注文を送らずに StateManager を更新する運用を想定。
    """
    def __init__(self, state_manager):
        self.state = state_manager
        self.exchange = None
        try:
            self.exchange = ccxt.bitget({
                "apiKey": BITGET_API_KEY,
                "secret": BITGET_API_SECRET,
                "password": BITGET_API_PASSPHRASE,
                "enableRateLimit": True,
            })
            # 一部 ccxt の bitget は futures を .set_sandbox_mode or options
            # ensure defaultType future/perpetual if supported:
            try:
                self.exchange.options['defaultType'] = 'swap'
            except Exception:
                pass
            logging.info("Initialized ccxt.bitget for futures.")
        except Exception as e:
            logging.warning("Could not initialize ccxt.bitget: %s", e)
            self.exchange = None

    # ---------- helpers ----------
    def _round_amount(self, symbol: str, amount: float) -> float:
        """
        Query market info to get min/max/precision; fallback to reasonable rounding.
        """
        try:
            markets = self.exchange.load_markets()
            m = markets.get(symbol) or markets.get(symbol.replace("/", "")) or None
            if m:
                step = m.get("limits", {}).get("amount", {}).get("min") or m.get("precision", {}).get("amount")
                if step:
                    return math.floor(amount / float(step)) * float(step)
                # fallback to precision
                p = m.get("precision", {}).get("amount")
                if p is not None:
                    fmt = "{:." + str(p) + "f}"
                    return float(fmt.format(amount))
        except Exception:
            pass
        # fallback: round to 6 decimals
        return float(round(amount, 6))

    def _market_symbol(self, symbol: str) -> str:
        """
        Convert e.g. 'BTC' to Bitget futures symbol used by ccxt: 'BTC/USDT:USDT' or 'BTC/USDT'
        We'll use 'BTC/USDT:USDT' which is common in bitget ccxt for swap.
        """
        return f"{symbol}/USDT:USDT"

    # ---------- open position ----------
    def open_position(self, symbol: str, side: str, size_usd: float, entry_price: float, take_profit: float,
                      stop_loss: float, leverage: float = 3.0, partial_steps: Optional[list] = None) -> Dict[str, Any]:
        """
        Open futures position (market) for given USD notional: size_usd -> amount units = size_usd / price
        side: 'long' or 'short'
        partial_steps: list of ratios for partial closes e.g. [0.5, 0.25, 0.25]
        Returns order / simulated result
        """
        symbol_pair = self._market_symbol(symbol)
        amount_asset = size_usd / float(entry_price) if entry_price > 0 else 0.0
        amount_asset = self._round_amount(symbol_pair, amount_asset)
        logging.info(f"Opening {side} {symbol} size_usd={size_usd:.2f} => amount={amount_asset:.6f} @ {entry_price:.6f}")

        if PAPER_TRADING or not self.exchange:
            # simulate: register in state
            self.state.open_position(symbol, side, entry_price, amount_asset, take_profit, stop_loss, leverage)
            logging.info(f"PAPER: simulated open {symbol} {side} amt={amount_asset}")
            return {"simulated": True, "symbol": symbol, "side": side, "amount": amount_asset}

        # live order flow (ccxt bitget)
        try:
            market_symbol = symbol_pair
            # set leverage if exchange supports via set_leverage method / private endpoint
            try:
                if hasattr(self.exchange, "set_leverage"):
                    # ccxt may require params: {'symbol': market_symbol, 'leverage': leverage}
                    self.exchange.set_leverage(leverage, market_symbol)
                else:
                    # Some exchanges need positionMarginMode or set margin mode
                    pass
            except Exception as e:
                logging.warning("Failed to set leverage: %s", e)

            # create market order: buy/sell depends on side and position direction; for futures we use create_order
            if side.lower() == "long":
                order = self.exchange.create_market_buy_order(market_symbol, amount_asset)
            else:
                order = self.exchange.create_market_sell_order(market_symbol, amount_asset)

            # Save position info in state with entry price from order response if available
            executed_price = order.get("average") or order.get("price") or entry_price
            self.state.open_position(symbol, side, executed_price, amount_asset, take_profit, stop_loss, leverage)
            return {"order": order}
        except Exception as e:
            logging.exception("Failed to place live order: %s", e)
            return {"error": str(e)}

    # ---------- close position (full or partial) ----------
    def close_position(self, symbol: str, portion: float = 1.0) -> Dict[str, Any]:
        """
        Close a portion of a position. portion: 0.0-1.0 (1.0 => all).
        If PAPER_TRADING, simulate exit at current price from exchange ticker.
        """
        if not self.state.has_position(symbol):
            raise KeyError("No open position to close for " + symbol)
        pos = self.state.get_positions().get(symbol)
        side = pos["side"]
        amt_total = float(pos["amount"])
        close_amount = amt_total * float(portion)
        market_sym = self._market_symbol(symbol)

        if PAPER_TRADING or not self.exchange:
            # simulate using current price
            price = None
            try:
                ticker = self.exchange.fetch_ticker(market_sym) if self.exchange else None
                price = ticker.get("last") if ticker else None
            except Exception:
                price = None
            if price is None:
                # fallback: use entry price as exit (zero PnL)
                price = float(pos["entry_price"])
            rec = self.state.close_position(symbol, price, reason=f"PAPER_CLOSE_{portion}")
            logging.info(f"PAPER: closed {portion*100:.0f}% of {symbol} at {price} -> pnl {rec['pnl']:.4f}")
            return {"simulated": True, "closed": portion, "pnl": rec["pnl"]}
        # live flow
        try:
            # decide order direction: to close long -> sell; to close short -> buy
            if side == "long":
                order = self.exchange.create_market_sell_order(market_sym, close_amount, {"reduceOnly": True})
            else:
                order = self.exchange.create_market_buy_order(market_sym, close_amount, {"reduceOnly": True})
            # Ideally verify executed price and record
            executed_price = order.get("average") or order.get("price")
            rec = self.state.close_position(symbol, executed_price, reason="LIVE_CLOSE")
            return {"order": order, "pnl": rec["pnl"]}
        except Exception as e:
            logging.exception("Failed to close position live: %s", e)
            return {"error": str(e)}
