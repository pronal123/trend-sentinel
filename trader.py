import ccxt
import logging
import asyncio
from config import EXCHANGE_API_KEY, EXCHANGE_API_SECRET, PAPER_TRADING_ENABLED
from database import get_open_position, log_trade_open, log_trade_close
from notifier import format_and_send_trade_notification

def initialize_exchange():
    """取引所オブジェクトを初期化する"""
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        logging.warning("Exchange API keys not set. Trading is disabled.")
        return None
    
    exchange = ccxt.binance({
        'apiKey': EXCHANGE_API_KEY, 'secret': EXCHANGE_API_SECRET,
        'options': {'defaultType': 'future'},
    })
    
    if PAPER_TRADING_ENABLED:
        logging.warning("PAPER TRADING IS ENABLED. Connecting to testnet.")
        exchange.set_sandbox_mode(True)
    else:
        logging.warning("LIVE TRADING IS ENABLED. Real funds will be used.")
    return exchange

exchange = initialize_exchange()

def execute_trade_logic(longs, shorts, overview):
    """分析結果を基に取引戦略を実行する"""
    if not exchange: return

    try:
        current_position = get_open_position()

        # --- ポジションクローズのロジック ---
        if current_position:
            symbol = current_position['symbol']
            is_long = current_position['side'] == 'long'
            close_signal = (is_long and shorts) or (not is_long and longs)
            
            if close_signal:
                logging.info(f"Close signal received for {symbol}. Closing position.")
                side = 'sell' if is_long else 'buy'
                amount = current_position['amount']
                
                # order = exchange.create_market_order(symbol, side, amount)
                # exit_price = float(order['price'])
                exit_price = longs[0]['priceUsd'] if not is_long else shorts[0]['priceUsd'] # ダミーの決済価格
                
                # 損益計算
                entry_price = current_position['entry_price']
                pnl = (exit_price - entry_price) * amount if is_long else (entry_price - exit_price) * amount
                pnl_percent = (pnl / (entry_price * amount)) * 100
                
                log_trade_close(symbol, exit_price, pnl)
                
                balance = exchange.fetch_balance()['USDT']['total']
                
                # 詳細な決済通知を送信
                trade_info = {
                    'type': 'close', 'symbol': symbol, 'pnl': pnl,
                    'pnl_percent': pnl_percent, 'balance': balance
                }
                asyncio.run(format_and_send_trade_notification(trade_info))
                return

        # --- 新規エントリーのロジック ---
        if not current_position:
            signal_to_trade, side = (longs[0], 'long') if longs and longs[0]['surge_probability'] > 0.85 else \
                                  (shorts[0], 'short') if shorts and shorts[0]['dump_probability'] > 0.85 else (None, None)
            
            if signal_to_trade:
                symbol = signal_to_trade['baseToken']['symbol'] + '/USDT'
                price = signal_to_trade['priceUsd']
                
                balance = exchange.fetch_balance()['USDT']['free']
                position_size_usdt = balance * 0.1
                amount = position_size_usdt / price
                
                order_side = 'buy' if side == 'long' else 'sell'
                logging.warning(f"Placing MARKET {order_side.upper()} order for {symbol}, Size: {amount:.4f}")
                # order = exchange.create_market_order(symbol, order_side, amount)
                # entry_price = float(order['price'])
                entry_price = price # ダミーの取得価格
                
                log_trade_open(symbol, side, amount, entry_price)
                
                # 損切りと利確ポイントの計算
                sl_price = entry_price * 0.95 if side == 'long' else entry_price * 1.05
                tp_price = entry_price * 1.05 if side == 'long' else entry_price * 0.95
                
                new_balance = exchange.fetch_balance()['USDT']['total']

                # 詳細な新規ポジション通知を送信
                trade_info = {
                    'type': 'open', 'symbol': symbol, 'side': side, 'amount': amount,
                    'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
                    'balance': new_balance
                }
                asyncio.run(format_and_send_trade_notification(trade_info))
                
    except ccxt.BaseError as e:
        logging.error(f"An error occurred in the trading logic: {e}")
    except Exception as e:
        logging.critical(f"A critical unexpected error occurred: {e}", exc_info=True)
