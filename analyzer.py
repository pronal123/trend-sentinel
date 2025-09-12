import pandas as pd
import logging
from database import check_if_recently_notified, record_notification
from ml_model import load_model, predict_probability

def analyze_and_detect_signals(all_pairs_data, db_conn):
    """
    取得した全データからシグナル候補とテクニカル指標を抽出する
    """
    surge_model, dump_model = load_model('surge'), load_model('dump')
    long_candidates, short_candidates = [], []

    if not all_pairs_data:
        return [], [], {}, {}

    df = pd.DataFrame(all_pairs_data)
    
    # (データクレンジング部分は変更なし)
    
    all_indicators = {}

    for _, token in df.iterrows():
        token_addr = token['baseToken']['address']
        if check_if_recently_notified(db_conn, token_addr): continue

        token_dict = token.to_dict()
        all_indicators[token_addr] = token_dict.get('indicators', {})
        
        token['surge_probability'] = predict_probability(surge_model, token_dict)
        if token['h24'] >= 12 and token['h1'] >= 5:
            long_candidates.append(token)
            
        token['dump_probability'] = predict_probability(dump_model, token_dict)
        if token['h24'] <= -8 and token['h1'] <= -3:
            short_candidates.append(token)

    # 上位候補を選出
    long_candidates = sorted(long_candidates, key=lambda x: x['surge_probability'], reverse=True)
    short_candidates = sorted(short_candidates, key=lambda x: x['dump_probability'], reverse=True)
    
    # 通知用にDB記録
    notification_candidates = (long_candidates[:3] if long_candidates else []) + \
                              (short_candidates[:3] if short_candidates else [])
    record_notification(db_conn, [t['baseToken']['address'] for t in notification_candidates])
    
    market_overview = {'監視銘柄数': len(df), '上昇': len(df[df['h24'] > 0]), '下落': len(df[df['h24'] < 0])}
    
    # `trader`に渡すためのシグナルと全指標を返す
    return long_candidates, short_candidates, all_indicators, market_overview
