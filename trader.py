import ccxt
import logging
import asyncio

# プロジェクト内の他モジュールをインポート
from config import (
    EXCHANGE_API_KEY,
    EXCHANGE_API_SECRET,
    PAPER_TRADING_ENABLED,
    POSITION_RISK_PERCENT,
    STOP_LOSS_PERCENT,
    TAKE_PROFIT_PERCENT
)
from database import get_open_position, log_trade_open, log_trade_close
# ✅ 修正点: 統一された通知関数をインポート
from notifier import format_and_send_notification
from strategy import make_final_trade_decision

def initialize_exchange():
    """取引所オブジェクトを初期化する"""
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        logging.warning("Exchange API keys are not set. Trading is disabled.")
        return None
    
    exchange = ccxt.binance({
        'apiKey': EXCHANGE_API_KEY,
        'secret': EXCHANGE_API_SECRET,
        'options': {
            'defaultType': 'future',
        },
    })
    
    if PAPER_TRADING_ENABLED:
        logging.warning("PAPER TRADING IS ENABLED. Connecting to testnet.")
        exchange.set_sandbox_mode(True)
    else:
        logging.warning("LIVE TRADING IS ENABLED. Real funds will be used.")
        
    return exchange

exchange = initialize_exchange()

def execute_trade_logic(longs, shorts, all_indicators, overview):
    """取引戦略の判断と注文実行を管理する"""
    if not exchange:
        return

    try:
        current_position = get_open_position()
        
        # --- クローズロジック ---
        if current_position:
            # (このサンプルでは、反対の強いシグナルが出た場合に決済するロジック)
            is_long = current_position['side'] == 'long'
            best_short = shorts[0] if shorts else None
            best_long = longs[0] if longs else None
            
            close_signal = None
            if is_long and best_short:
                close_signal = {'type': 'short', **best_short}
            elif not is_long and best_long:
                close_signal = {'type': 'long', **best_long}

            if close_signal:
                logging.info(f"Close signal received for {current_position['symbol']}. Closing position.")
                # ... (実際の決済注文ロジックをここに追加) ...
                
                # ダミーの決済価格と損益計算
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


        # --- 新規エントリーロジック ---
        if not current_position:
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
                # ✅ 修正点: 統一された関数を正しく呼び出す
                asyncio.run(format_and_send_notification(trade_info, notification_type='trade'))

    except ccxt.BaseError as e:
        logging.error(f"An exchange error occurred in the trading logic: {e}")
    except Exception as e:
        logging.critical(f"A critical unexpected error occurred in trader: {e}", exc_info=True)
