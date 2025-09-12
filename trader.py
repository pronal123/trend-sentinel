import ccxt
import logging
from config import EXCHANGE_API_KEY, EXCHANGE_API_SECRET, PAPER_TRADING_ENABLED

# --- グローバル変数 ---
# 本番環境ではデータベースで永続化する必要があります
current_position = {} 

def initialize_exchange():
    """取引所オブジェクトを初期化する"""
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        logging.warning("Exchange API keys are not set. Trading is disabled.")
        return None
    
    exchange = ccxt.binance({
        'apiKey': EXCHANGE_API_KEY,
        'secret': EXCHANGE_API_SECRET,
        'options': {
            'defaultType': 'future', # 先物取引をデフォルトに設定
        },
    })
    
    # ペーパー取引が有効な場合は、テストネットに接続
    if PAPER_TRADING_ENABLED:
        logging.warning("PAPER TRADING IS ENABLED. Connecting to testnet.")
        exchange.set_sandbox_mode(True)
    else:
        logging.warning("LIVE TRADING IS ENABLED. Real funds will be used.")
        
    return exchange

exchange = initialize_exchange()

def execute_trade_logic(longs, shorts, overview):
    """分析結果を基に取引戦略を実行する"""
    global current_position
    if not exchange: return

    try:
        # --- ポジションクローズのロジック ---
        if current_position:
            symbol = current_position['symbol']
            # (ここでは単純化のため、反対のシグナルが出たらクローズするロジック)
            is_long = current_position['side'] == 'long'
            close_signal = (is_long and shorts) or (not is_long and longs)
            
            if close_signal:
                logging.info(f"Close signal received for {symbol}. Closing position.")
                # 反対売買でポジションをクローズ
                side = 'sell' if is_long else 'buy'
                # exchange.create_market_order(symbol, side, current_position['amount'])
                current_position = {} # ポジション情報をリセット
                return # このサイクルでは新規エントリーしない

        # --- 新規エントリーのロジック ---
        if not current_position:
            signal_to_trade = None
            side = None
            
            if longs and longs[0]['surge_probability'] > 0.85: # 85%以上の確度でLONG
                signal_to_trade = longs[0]
                side = 'long'
            elif shorts and shorts[0]['dump_probability'] > 0.85: # 85%以上の確度でSHORT
                signal_to_trade = shorts[0]
                side = 'short'
            
            if signal_to_trade:
                symbol = signal_to_trade['baseToken']['symbol'] + '/USDT'
                price = signal_to_trade['priceUsd']
                
                # --- リスク管理：ポジションサイズの計算 ---
                balance = exchange.fetch_balance()
                usdt_balance = balance['USDT']['free']
                position_size_usdt = usdt_balance * 0.1 # 常に残高の10%をリスクに晒す
                amount = position_size_usdt / price
                
                # --- 注文実行 ---
                order_side = 'buy' if side == 'long' else 'sell'
                logging.warning(f"Placing MARKET {order_side.upper()} order for {symbol}, Size: {amount:.4f}")
                # order = exchange.create_market_order(symbol, order_side, amount)
                
                # --- リスク管理：損切り注文 ---
                stop_loss_price = price * 0.95 if side == 'long' else price * 1.05 # 5%の損切り
                stop_loss_side = 'sell' if side == 'long' else 'buy'
                logging.warning(f"Placing STOP LOSS order for {symbol} at {stop_loss_price:.4f}")
                # exchange.create_order(symbol, 'stop_market', stop_loss_side, amount, params={'stopPrice': stop_loss_price})
                
                # ポジション情報を記録
                current_position = {
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'entry_price': price
                }
    except ccxt.BaseError as e:
        logging.error(f"An error occurred in the trading logic: {e}")
    except Exception as e:
        logging.critical(f"A critical unexpected error occurred: {e}", exc_info=True)

