# strategy.py
import logging
from config import ADX_THRESHOLD, AI_CONFIDENCE_THRESHOLD

def make_trade_decision(signal, indicators):
    """
    シグナルとテクニカル指標に基づき、最終的な取引判断を行う
    
    Returns:
        str or None: 'LONG', 'SHORT', または None (取引見送り)
    """
    if not signal or not indicators:
        return None

    # --- 1. マーケット状況の認識 (レジームフィルター) ---
    adx = indicators.get('adx_14', 0)
    if adx < ADX_THRESHOLD:
        logging.info(f"Sideways market detected (ADX: {adx:.2f}). No trade.")
        return None # レンジ相場では取引しない

    # --- 2. 複数時間軸での分析 (長期トレンドフィルター) ---
    long_term_trend = indicators.get('long_term_trend')
    
    trade_side = None
    if signal['type'] == 'long' and signal['surge_probability'] > AI_CONFIDENCE_THRESHOLD:
        if long_term_trend == 'UP':
            logging.info("Long signal confirmed by long-term uptrend.")
            trade_side = 'LONG'
        else:
            logging.info("Long signal ignored due to long-term downtrend/sideways.")
    
    elif signal['type'] == 'short' and signal['dump_probability'] > AI_CONFIDENCE_THRESHOLD:
        if long_term_trend == 'DOWN':
            logging.info("Short signal confirmed by long-term downtrend.")
            trade_side = 'SHORT'
        else:
            logging.info("Short signal ignored due to long-term uptrend/sideways.")
    
    if not trade_side:
        return None

    # --- 3. エントリー精度の向上 (支持線・抵抗線フィルター) ---
    # ここでは概念のみ。価格が支持線/抵抗線に近づいたかどうかの判定ロジックが必要。
    # last_price = signal['priceUsd']
    # support = indicators.get('support_1', 0)
    # if trade_side == 'LONG' and last_price > support * 1.01: # まだ支持線から遠い
    #     logging.info("Waiting for pullback to support level for LONG entry.")
    #     return None # 押し目待ち

    return trade_side
