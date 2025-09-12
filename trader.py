import ccxt
import logging
import asyncio
from config import *
from database import get_open_position, log_trade_open, log_trade_close
from notifier import format_and_send_trade_notification
from strategy import make_trade_decision

# (initialize_exchange関数は変更なし)
# ...

def execute_trade_logic(signals, indicators):
    """取引戦略の判断と注文実行を管理する"""
    if not exchange: return

    try:
        current_position = get_open_position()
        
        # --- クローズロジック ---
        if current_position:
            # (損切り/利確は取引所が管理。ここでは反対シグナルでの決済ロジック)
            close_decision = None
            if current_position['side'] == 'long' and signals.get('best_short'):
                close_decision = make_trade_decision(signals['best_short'], indicators)
            elif current_position['side'] == 'short' and signals.get('best_long'):
                close_decision = make_trade_decision(signals['best_long'], indicators)
            
            if close_decision:
                # ... (決済注文と通知のロジック)
                return

        # --- 新規エントリーロジック ---
        if not current_position:
            # LONGとSHORTどちらのシグナルが強いか判断
            best_signal = None
            if signals.get('best_long') and signals.get('best_short'):
                if signals['best_long']['surge_probability'] > signals['best_short']['dump_probability']:
                    best_signal = signals['best_long']
                else:
                    best_signal = signals['best_short']
            elif signals.get('best_long'):
                best_signal = signals['best_long']
            elif signals.get('best_short'):
                best_signal = signals['best_short']

            if not best_signal: return

            # 戦略モジュールに最終判断を委ねる
            decision = make_trade_decision(best_signal, indicators)

            if decision in ['LONG', 'SHORT']:
                symbol = best_signal['baseToken']['symbol'] + '/USDT'
                price = best_signal['priceUsd']
                
                # リスク管理と注文実行
                balance = exchange.fetch_balance()['USDT']['free']
                position_size_usdt = balance * POSITION_RISK_PERCENT
                amount = position_size_usdt / price
                
                order_side = 'buy' if decision == 'LONG' else 'sell'
                sl_price = price * (1 - STOP_LOSS_PERCENT) if decision == 'LONG' else price * (1 + STOP_LOSS_PERCENT)
                tp_price = price * (1 + TAKE_PROFIT_PERCENT) if decision == 'LONG' else price * (1 - TAKE_PROFIT_PERCENT)
                
                logging.warning(f"Strategy decided: {decision}. Placing order for {symbol}.")
                # order = exchange.create_market_order(symbol, order_side, amount)
                # exchange.create_order(symbol, 'stop_market', 'sell', amount, params={'stopPrice': sl_price})
                # exchange.create_order(symbol, 'take_profit_market', 'sell', amount, params={'stopPrice': tp_price})
                
                log_trade_open(symbol, decision.lower(), amount, price)
                
                # 通知
                trade_info = {
                    'type': 'open', 'symbol': symbol, 'side': decision.lower(), 'amount': amount,
                    'entry_price': price, 'sl_price': sl_price, 'tp_price': tp_price,
                    'balance': balance
                }
                asyncio.run(format_and_send_trade_notification(trade_info))

    except Exception as e:
        logging.critical(f"A critical error occurred in trader: {e}", exc_info=True)
