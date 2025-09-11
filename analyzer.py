import pandas as pd
import logging
from database import check_if_recently_notified, record_notification
from ml_model import load_model, predict_probability # 関数名を変更

def analyze_and_detect_signals(all_pairs_data, db_conn):
    """データ分析とシグナル検知のコアロジック"""
    surge_model = load_model('surge') # 上昇モデルをロード
    dump_model = load_model('dump')   # 下落モデルをロード

    long_candidates, short_candidates = [], []

    if not all_pairs_data:
        return [], [], {'監視銘柄数': 0, '上昇': 0, '下落': 0}

    df = pd.DataFrame(all_pairs_data)
    
    # データクレンジング
    for col in ['h1', 'h24']:
        df[col] = pd.to_numeric(df['priceChange'].apply(lambda x: x.get(col) if isinstance(x, dict) else 0), errors='coerce').fillna(0)
    df['volume_h24'] = pd.to_numeric(df['volume'].apply(lambda x: x.get('h24') if isinstance(x, dict) else 0), errors='coerce').fillna(0)
    
    total_monitored = len(df)
    
    for _, token in df.iterrows():
        token_addr = token['baseToken']['address']
        if check_if_recently_notified(db_conn, token_addr): continue

        token_dict = token.to_dict()
        
        # --- LONG候補の分析 ---
        surge_prob = predict_probability(surge_model, token_dict)
        token['surge_probability'] = surge_prob
        
        if token['h24'] >= 12 and token['h1'] >= 5 and token['volume_h24'] > 100000 and surge_prob > 0.6:
            long_candidates.append(token)
            
        # --- SHORT候補の分析 ---
        dump_prob = predict_probability(dump_model, token_dict)
        token['dump_probability'] = dump_prob
        
        # ✅ 検知ロジックにAIスコアを追加
        if token['h24'] <= -8 and token['h1'] <= -3 and token['volume_h24'] > 100000 and dump_prob > 0.6:
            short_candidates.append(token)

    # 上位を選出
    long_candidates = sorted(long_candidates, key=lambda x: x['surge_probability'], reverse=True)[:3]
    short_candidates = sorted(short_candidates, key=lambda x: x['dump_probability'], reverse=True)[:3] # スコア順に変更
    
    with db_conn:
        for t in long_candidates + short_candidates:
            record_notification(db_conn, t['baseToken']['address'])
    
    market_overview = {
        '監視銘柄数': total_monitored,
        '上昇': len(df[df['h24'] > 0]),
        '下落': len(df[df['h24'] < 0]),
    }
    
    return long_candidates, short_candidates, market_overview
