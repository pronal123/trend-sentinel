import ccxt
import logging
import asyncio

# Project modules
from config import (
    EXCHANGE_NAME,
    EXCHANGE_API_KEY,
    EXCHANGE_API_SECRET,
    EXCHANGE_API_PASSPHRASE,
    PAPER_TRADING_ENABLED,
    POSITION_RISK_PERCENT,
    STOP_LOSS_PERCENT,
    TAKE_PROFIT_PERCENT
)
from database import get_open_position, log_trade_open, log_trade_close
from notifier import format_and_send_notification
from strategy import make_final_trade_decision

def initialize_exchange():
    """Initializes the exchange object."""
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        logging.warning("Exchange API keys are not set. Trading is disabled.")
        return None
    
    try:
        exchange_class = getattr(ccxt, EXCHANGE_NAME)
    except AttributeError:
        logging.error(f"Exchange '{EXCHANGE_NAME}' is not supported by ccxt.")
        return None

    config = {
        'apiKey': EXCHANGE_API_KEY,
        'secret': EXCHANGE_API_SECRET,
        'options': {'defaultType': 'future'},
    }
    
    if EXCHANGE_NAME == 'bitget':
        config['password'] = EXCHANGE_API_PASSPHRASE

    exchange = exchange_class(config)
    
    if PAPER_TRADING_ENABLED:
        logging.warning(f"PAPER TRADING IS ENABLED. Connecting to {EXCHANGE_NAME} testnet.")
        try:
            exchange.set_sandbox_mode(True)
        except ccxt.NotSupported:
            logging.error(f"{EXCHANGE_NAME} does not support sandbox mode via ccxt. Trading disabled for safety.")
            return None
    else:
        logging.warning(f"LIVE TRADING IS ENABLED on {EXCHANGE_NAME}. Real funds will be used.")
        
    return exchange

exchange = initialize_exchange()

def execute_trade_logic(longs, shorts, all_indicators, overview):
    """Manages trade strategy decisions and order execution."""
    if not exchange:
        return

    try:
        global exchange
        
        current_position = get_open_position()
        
        # --- Close Logic ---
        if current_position:
            is_long = current_position['side'] == 'long'
            best_short = shorts[0] if shorts else None
            best_long = longs[0] if longs else None
            
            close_signal = None
            if is_long and best_short:
                close_signal = {'type': 'short', **best_short}
            elif not is_long and best_long:
                close_signal = {'type': 'long', **best_long}

            if close_signal:
                logging.info(f"Close signal for {current_position['symbol']}. Closing.")
                exit_price = close_signal['priceUsd']
                entry_price = current_position['entry_price']
                amount = current_position['amount']
                pnl = (exit_price - entry_price) * amount if is_long else (entry_price - exit_price) * amount
                pnl_percent = (pnl / (entry_price * amount)) * 100
                
                log_trade_close(current_position['symbol'], exit_price, pnl)
                balance = exchange.fetch_balance()['USDT']['total']
                
                trade_info = {'type': 'close', 'symbol': current_position['symbol'], 'pnl': pnl, 'pnl_percent': pnl_percent, 'balance': balance}
                asyncio.run(format_and_send_notification(trade_info, notification_type='trade'))
                return

        # --- New Entry Logic ---
        if not current_position:
            # ✅ 修正: ここに 'pass' を追加してインデントエラーを回避
            pass 
            # (Logic to select best signal is unchanged)
            # ...
            best_signal = None
            best_long = longs[0] if longs else None
            best_short = shorts[0] if shorts else None

            if best_long and best_short:
                if best_long['surge_probability'] > best_short['dump_probability']:
                    best_signal = {'type': 'long', **best_long}
                else:
                    best_signal = {'type': 'short', **best_short}
            elif best_long:
                best_signal = {'type': 'long', **best_long}
            elif best_short:
                best_signal = {'type': 'short', **best_short}

            if not best_signal:
                return

            token_addr = best_signal['baseToken']['address']
            indicators = all_indicators.get(token_addr, {})

            decision = make_final_trade_decision(best_signal, indicators, exchange)

            if decision in ['LONG', 'SHORT']:
                symbol = best_signal['baseToken']['symbol'] + '/USDT'
                price = best_signal['priceUsd']
                
                balance = exchange.fetch_balance()['USDT']['free']
                position_size_usdt = balance * POSITION_RISK_PERCENT
                amount = position_size_usdt / price
                
                order_side = 'buy' if decision == 'LONG' else 'sell'
                sl_price = price * (1 - STOP_LOSS_PERCENT) if decision == 'LONG' else price * (1 + STOP_LOSS_PERCENT)
                tp_price = price * (1 + TAKE_PROFIT_PERCENT) if decision == 'LONG' else price * (1 - TAKE_PROFIT_PERCENT)
                
                logging.warning(f"Strategy approved: {decision}. Placing order for {symbol}.")
                
                # --- 実際の注文実行 (テスト中はコメントアウト推奨) ---
                # market_order = exchange.create_market_order(symbol, order_side, amount)
                # entry_price = float(market_order['price'])
                # stop_loss_side = 'sell' if decision == 'LONG' else 'buy'
                # exchange.create_order(symbol, 'stop_market', stop_loss_side, amount, params={'stopPrice': sl_price})
                
                entry_price = price # ダミー価格で代用
                log_trade_open(symbol, decision.lower(), amount, entry_price)
                
                trade_info = {
                    'type': 'open', 'symbol': symbol, 'side': decision.lower(), 'amount': amount,
                    'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
                    'balance': balance
                }
                asyncio.run(format_and_send_notification(trade_info, notification_type='trade'))


    except ccxt.NotSupported:
        logging.error(f"The configured exchange '{EXCHANGE_NAME}' does not support a required feature. Disabling trading.")
        exchange = None # Modify the global variable
    except ccxt.BaseError as e:
        logging.error(f"An exchange error occurred in the trading logic: {e}")
    except Exception as e:
        logging.critical(f"A critical unexpected error occurred in trader: {e}", exc_info=True)
