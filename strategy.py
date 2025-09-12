import logging
from config import ADX_THRESHOLD, AI_CONFIDENCE_THRESHOLD

def run_simplified_strategy(signal):
    """詳細データがない場合に使用する、シンプルな戦略"""
    logging.warning(f"Running SIMPLIFIED strategy for {signal['baseToken']['symbol']} due to missing indicator data.")
    
    signal_side = signal['type']
    confidence = signal.get('surge_probability') if signal_side == 'long' else signal.get('dump_probability', 0)
    
    if confidence > AI_CONFIDENCE_THRESHOLD:
        logging.info(f"Simplified strategy: AI confidence ({confidence:.1%}) is high. Approving trade.")
        return signal_side.upper()
    
    return None

def run_full_strategy(signal, indicators, exchange):
    """全てのデータが揃っている場合に使用する、高度な戦略"""
    logging.info(f"Running FULL strategy for {signal['baseToken']['symbol']}.")
    
    signal_side = signal['type']

    # --- 1. マーケット状況の認識 (レジームフィルター) ---
    adx = indicators.get('adx_14', 0)
    if adx < ADX_THRESHOLD:
        logging.info(f"FULL STRATEGY REJECT: Sideways market (ADX: {adx:.2f}).")
        return None

    # --- 2. 複数時間軸での分析 (長期トレンドフィルター) ---
    long_term_trend = indicators.get('long_term_trend')
    if (signal_side == 'long' and long_term_trend != 'UP') or \
       (signal_side == 'short' and long_term_trend != 'DOWN'):
        logging.info(f"FULL STRATEGY REJECT: Signal direction conflicts with long-term trend ({long_term_trend}).")
        return None
        
    # (オーダーブック分析などの、さらに高度なフィルターをここに追加)

    logging.warning(f"FINAL DECISION: All filters passed. Approving {signal_side.upper()} trade.")
    return signal_side.upper()

def make_final_trade_decision(signal, indicators, exchange):
    """
    データの利用可能性に応じて、適切な戦略判断を行う司令塔
    """
    # --- ステップ1: AIスコアの基本フィルタリング ---
    signal_side = signal['type']
    confidence = signal.get('surge_probability') if signal_side == 'long' else signal.get('dump_probability', 0)
    if confidence < AI_CONFIDENCE_THRESHOLD:
        return None # AIの確度が低い場合は、どの戦略も実行しない

    # --- ステップ2: ✅ 適応型ロジック ---
    # ADXや長期トレンドなど、詳細な指標が計算できたかを確認
    if indicators and 'adx_14' in indicators and 'long_term_trend' in indicators:
        # 詳細データがある -> フル戦略を実行
        return run_full_strategy(signal, indicators, exchange)
    else:
        # 詳細データがない -> シンプルな戦略を実行
        return run_simplified_strategy(signal)
