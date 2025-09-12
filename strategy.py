# strategy.py (修正後のフルコード)
import logging
from config import ADX_THRESHOLD, AI_CONFIDENCE_THRESHOLD
from database import log_signal_decision # ✅ インポート

def run_simplified_strategy(signal):
    """詳細データがない場合に使用する、シンプルな戦略"""
    logging.warning(f"Running SIMPLIFIED strategy for {signal['baseToken']['symbol']} due to missing indicator data.")
    
    signal_side = signal['type']
    confidence = signal.get('surge_probability') if signal_side == 'long' else signal.get('dump_probability', 0)
    
    rejection_reason = None
    decision = None

    if confidence > AI_CONFIDENCE_THRESHOLD:
        logging.info(f"Simplified strategy: AI confidence ({confidence:.1%}) is high. Approving trade.")
        decision = signal_side.upper()
    else:
        rejection_reason = f"AI Confidence ({confidence:.1%}) below threshold ({AI_CONFIDENCE_THRESHOLD:.1%})"
        decision = "REJECTED"

    # ✅ シグナルログを記録
    log_signal_decision(
        signal['baseToken']['address'],
        signal['baseToken']['symbol'],
        signal_side,
        confidence,
        signal['priceUsd'],
        "Approved" if decision == signal_side.upper() else "Rejected",
        rejection_reason
    )
    
    return decision if decision == signal_side.upper() else None

def run_full_strategy(signal, indicators, exchange):
    """全てのデータが揃っている場合に使用する、高度な戦略"""
    logging.info(f"Running FULL strategy for {signal['baseToken']['symbol']}.")
    
    signal_side = signal['type']
    confidence = signal.get('surge_probability') if signal_side == 'long' else signal.get('dump_probability', 0)
    symbol = signal['baseToken']['symbol']
    token_address = signal['baseToken']['address']
    price_usd = signal['priceUsd']

    rejection_reason = []
    
    # --- 1. マーケット状況の認識 (レジームフィルター) ---
    adx = indicators.get('adx_14', 0)
    if adx < ADX_THRESHOLD:
        rejection_reason.append(f"Sideways market (ADX: {adx:.2f} < {ADX_THRESHOLD})")

    # --- 2. 複数時間軸での分析 (長期トレンドフィルター) ---
    long_term_trend = indicators.get('long_term_trend')
    if (signal_side == 'long' and long_term_trend != 'UP') or \
       (signal_side == 'short' and long_term_trend != 'DOWN'):
        rejection_reason.append(f"Long-term trend ({long_term_trend}) conflicts with signal ({signal_side})")
        
    # (オーダーブック分析などの、さらに高度なフィルターをここに追加)

    final_decision = None
    if not rejection_reason: # 全てのフィルターを通過した場合
        logging.warning(f"FULL STRATEGY APPROVED: All filters passed. Approving {signal_side.upper()} trade for {symbol}.")
        final_decision = signal_side.upper()
        # ✅ シグナルログを記録
        log_signal_decision(token_address, symbol, signal_side, confidence, price_usd, "Approved")
    else:
        logging.info(f"FULL STRATEGY REJECTED for {symbol}: {'; '.join(rejection_reason)}")
        # ✅ シグナルログを記録
        log_signal_decision(token_address, symbol, signal_side, confidence, price_usd, "Rejected", '; '.join(rejection_reason))
    
    return final_decision

def make_final_trade_decision(signal, indicators, exchange):
    """
    データの利用可能性に応じて、適切な戦略判断を行う司令塔
    """
    # --- ステップ1: AIスコアの基本フィルタリング ---
    signal_side = signal['type']
    confidence = signal.get('surge_probability') if signal_side == 'long' else signal.get('dump_probability', 0)
    
    if confidence < AI_CONFIDENCE_THRESHOLD:
        rejection_reason = f"AI Confidence ({confidence:.1%}) below threshold ({AI_CONFIDENCE_THRESHOLD:.1%})"
        # ✅ シグナルログを記録 (AIフィルターで即却下された場合)
        log_signal_decision(
            signal['baseToken']['address'],
            signal['baseToken']['symbol'],
            signal_side,
            confidence,
            signal['priceUsd'],
            "Rejected",
            rejection_reason
        )
        return None # AIの確度が低い場合は、どの戦略も実行しない

    # --- ステップ2: ✅ 適応型ロジック ---
    # ADXや長期トレンドなど、詳細な指標が計算できたかを確認
    if indicators and 'adx_14' in indicators and 'long_term_trend' in indicators:
        # 詳細データがある -> フル戦略を実行
        return run_full_strategy(signal, indicators, exchange)
    else:
        # 詳細データがない -> シンプルな戦略を実行
        return run_simplified_strategy(signal)

