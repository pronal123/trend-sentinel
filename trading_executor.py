# trading_executor.py
import os
import logging
import math
from typing import Optional, Dict, Any

import ccxt

logger = logging.getLogger(__name__)


class TradingExecutor:
    """
    Bitget Futures (USDT perpetual) を想定した実注文ラッパー。
    PAPER_TRADING 環境変数でトレードをシミュレーション可能。
    """

    def __init__(self):
        self.api_key = os.getenv("BITGET_API_KEY")
        self.api_secret = os.getenv("BITGET_API_SECRET")
        self.api_password = os.getenv("BITGET_API_PASSWORD", "")
        self.paper_trading = os.getenv("PAPER_TRADING", "True") in ["True", "true", "1"]
        # ccxt exchange (futures default)
        self.exchange = None
        try:
            self.exchange = ccxt.bitget({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "password": self.api_password,
                "enableRateLimit": True,
                "options": {"defaultType": "swap"}
            })
            logger.info("Initialized ccxt.bitget for futures.")
        except Exception as e:
            logger.warning("Failed to init ccxt.bitget: %s", e)
            self.exchange = None

    def _market_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.exchange:
            return None
        try:
            m = self.exchange.load_markets()
            return self.exchange.market(symbol)
        except Exception as e:
            logger.debug("market_info fetch failed: %s", e)
            return None

    def _round_amount(self, symbol: str, amount_asset: float) -> float:
        """
        取引所の最小数量刻みで丸める
        """
        market = self._market_info(symbol)
        if not market:
            return round(amount_asset, 8)
        step = market.get("precision", {}).get("amount")
        if step is None:
            step = market.get("limits", {}).get("amount", {}).get("min", 0.000001)
        # step might be decimal places; try to round to step's decimal places
        try:
            step = float(step)
            if step <= 0:
                return round(amount_asset, 8)
            # compute decimals
            decimals = max(0, int(-math.floor(math.log10(step)))) if step < 1 else 0
            rounded = math.floor(amount_asset / step) * step
            return round(rounded, decimals)
        except Exception:
            return round(amount_asset, 8)

    def set_leverage(self, symbol: str, leverage: int = 10):
        """
        CCXTのset_leverage が使えるなら呼ぶ。取引所によりパラメータが異なる。
        """
        if self.paper_trading or not self.exchange:
            logger.debug("[PAPER] set_leverage skipped")
            return
        try:
            # ccxt may have set_leverage
            self.exchange.set_leverage(leverage, symbol)
            logger.info("Set leverage %sx for %s", leverage, symbol)
        except Exception as e:
            logger.warning("set_leverage failed: %s", e)

    def create_market_order(self, symbol: str, side: str, size_asset: float, reduce_only: bool = False) -> Dict:
        """
        実市場にマーケット注文を送る (futures)。
        side: 'long' -> 'buy' to open long; 'short' -> 'sell' to open short (depends on exchange convention)
        size_asset: asset quantity
        """
        if self.paper_trading:
            logger.info(f"[PAPER] create_market_order: {symbol} {side} size={size_asset}")
            return {"id": "paper_order", "symbol": symbol, "side": side, "size": size_asset}

        if not self.exchange:
            raise RuntimeError("Exchange not initialized")

        # ccxt create_order requires side buy/sell
        ccxt_side = "buy" if side.lower() == "long" else "sell"
        amount = self._round_amount(symbol, size_asset)
        try:
            params = {"reduceOnly": reduce_only}
            order = self.exchange.create_order(symbol, "market", ccxt_side, amount, None, params)
            logger.info("Order result: %s", order)
            return order
        except Exception as e:
            logger.error("create_market_order failed: %s", e)
            raise

    def close_position_market(self, symbol: str, pos_side: str, size_asset: float) -> Dict:
        """
        ポジションを市場でクローズ（全量or一部）する。
        pos_side is current position side ('long' or 'short'). To close a long -> sell, to close short -> buy.
        """
        if self.paper_trading:
            logger.info(f"[PAPER] close_position_market: {symbol} {pos_side} size={size_asset}")
            return {"id": "paper_close"}
        if not self.exchange:
            raise RuntimeError("Exchange not initialized")
        # To close a long, we send sell; to close short, we send buy
        side = "sell" if pos_side.lower() == "long" else "buy"
        try:
            amount = self._round_amount(symbol, size_asset)
            params = {"reduceOnly": True}
            order = self.exchange.create_order(symbol, "market", side, amount, None, params)
            logger.info("Close order: %s", order)
            return order
        except Exception as e:
            logger.error("close_position_market failed: %s", e)
            raise
