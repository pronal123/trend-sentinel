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
from notifier import format_and_send_trade_notification
from strategy import make_final_trade_decision # 新しい戦略判断関数をインポート

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
            # ここではポジションをクローズするためのロジックを実装します。
            # 例: 反対のシグナルが出た場合、またはSL/TPに達した場合（取引所からの情報取得が必要）
            # 今回は新規エントリーに焦点を当てるため、省略します。
            pass

        # --- 新規エントリーロジック ---
        if not current_position:
            best_long = longs[0] if longs else None
            best_short = shorts[0] if shorts else None
            
            signal_to_consider = None
            
            # AIスコアが最も高いシグナルを最優先候補として選択
            if best_long and best_short:
                if best_long['surge_probability'] > best_short['dump_probability']:
                    signal_to_consider = {'type': 'long', **best_long}
                else:
                    signal_to_consider = {'type': 'short', **best_short}
            elif best_long:
                signal_to_consider = {'type': 'long', **best_long}
            elif best_short:
                signal_to_consider = {'type': 'short', **best_short}

            if not signal_to_consider:
                logging.info("No high-confidence signal to consider.")
                return

            # 対応するトークンのテクニカル指標を取得
            token_addr = signal_to_consider['baseToken']['address']
            indicators = all_indicators.get(token_addr, {})

            # ✅ 修正点: 新しい戦略モジュールに最終判断を委ねる
            decision = make_final_trade_decision(signal_to_consider, indicators, exchange)

            if decision in ['LONG', 'SHORT']:
                symbol = signal_to_consider['baseToken']['symbol'] + '/USDT'
                price = signal_to_consider['priceUsd']
                
                # リスク管理と注文実行
                balance = exchange.fetch_balance()['USDT']['free']
                position_size_usdt = balance * POSITION_RISK_PERCENT
                amount = position_size_usdt / price
                
                order_side = 'buy' if decision == 'LONG' else 'sell'
                sl_price = price * (1 - STOP_LOSS_PERCENT) if decision == 'LONG' else price * (1 + STOP_LOSS_PERCENT)
                tp_price = price * (1 + TAKE_PROFIT_PERCENT) if decision == 'LONG' else price * (1 - TAKE_PROFIT_PERCENT)
                
                logging.warning(f"Strategy approved: {decision}. Placing order for {symbol}.")
                
                # --- 実際の注文実行部分 (テスト中はコメントアウト) ---
                # logging.info(f"Executing MARKET {order_side.upper()} order for {symbol}, Size: {amount:.4f}")
                # market_order = exchange.create_market_order(symbol, order_side, amount)
                # entry_price = float(market_order['price'])
                
                # logging.info(f"Executing STOP LOSS order for {symbol} at {sl_price:.4f}")
                # stop_loss_side = 'sell' if decision == 'LONG' else 'buy'
                # exchange.create_order(symbol, 'stop_market', stop_loss_side, amount, params={'stopPrice': sl_price})
                # --- 注文実行ここまで ---
                
                entry_price = price # ダミー価格で代用
                log_trade_open(symbol, decision.lower(), amount, entry_price)
                
                # 取引詳細をTelegramに通知
                trade_info = {
                    'type': 'open', 'symbol': symbol, 'side': decision.lower(), 'amount': amount,
                    'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
                    'balance': balance
                }
                # 非同期関数を同期的に呼び出す
                asyncio.run(format_and_send_trade_notification(trade_info))

    except ccxt.BaseError as e:
        logging.error(f"An exchange error occurred in the trading logic: {e}")
    except Exception as e:
        logging.critical(f"A critical unexpected error occurred in trader: {e}", exc_info=True)
