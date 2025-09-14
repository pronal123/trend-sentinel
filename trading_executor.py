# trading_executor.py (抜粋)

class TradingExecutor:
    def __init__(self, state_manager):
        import ccxt
        self.exchange = ccxt.bitget({
            "apiKey": os.getenv("BITGET_API_KEY"),
            "secret": os.getenv("BITGET_API_SECRET"),
            "password": os.getenv("BITGET_API_PASSPHRASE"),
            "enableRateLimit": True,
        })
        self.state = state_manager

    def open_position(self, side, symbol, series, score, notifier, analysis_comment, position_size_usd, market_type="spot"):
        """
        side: "LONG" or "SHORT"
        market_type: "spot" or "futures"
        """
        try:
            # switch defaultType
            if market_type == "spot":
                self.exchange.options["defaultType"] = "spot"
            elif market_type == "futures":
                self.exchange.options["defaultType"] = "swap"
            else:
                raise ValueError("market_type must be spot or futures")

            # decide amount (simplified)
            price = float(series['close'].iloc[-1]) if not series.empty else self.exchange.fetch_ticker(symbol)["last"]
            amount = round(position_size_usd / price, 6)

            if side == "LONG":
                order = self.exchange.create_market_buy_order(symbol, amount)
            else:
                order = self.exchange.create_market_sell_order(symbol, amount)

            # record to state
            self.state.add_position(symbol, {
                "side": side,
                "amount": amount,
                "entry_price": price,
                "market_type": market_type,
                "comment": analysis_comment,
            })

            notifier.send(f"<b>注文成功</b> ✅ {symbol} | {market_type.upper()} {side} | Size: ${position_size_usd:.2f}")
            return order
        except Exception as e:
            notifier.send(f"<b>注文失敗</b> ❌ {symbol} | {market_type.upper()} {side} | Error: {e}")
            raise
