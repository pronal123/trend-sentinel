import pandas as pd
import logging
import sqlite3

# 関連モジュールから必要な関数をインポート
from database import check_if_recently_notified, record_notification
from ml_model import load_model, predict_surge_probability

def analyze_and_detect_signals(all_pairs_data, db_conn):
    """
    データ分析とシグナル検知のコアロジック。
    この関数が main.py から呼び出される。
    """
    model = load_model()
    long_candidates, short_candidates = [], []

    if not all_pairs_data:
        return [], [], [], {}
        
    df = pd.DataFrame(all_pairs_data)
    
    # データクレンジング
    for col in ['h1', 'h24']:
        df[col] = pd.to_numeric(df['priceChange'].apply(lambda x: x.get(col) if isinstance(x, dict) else 0), errors='coerce').fillna(0)
    df['volume_h24'] = pd.to_numeric(df['volume'].apply(lambda x: x.get('h24') if isinstance(x, dict) else 0), errors='coerce').fillna(0)
    
    total_monitored = len(df)
    
    for _, token in df.iterrows():
        token_addr = token['baseToken']['address']
        
        # 最近通知済みかチェック
        if check_if_recently_notified(db_conn, token_addr):
            continue

        # MLモデルで急騰確率を予測
        surge_prob = predict_surge_probability(model, token.to_dict())
        token['surge_probability'] = surge_prob
        
        # --- 検知ロジック ---
        # LONG候補
        if token['h24'] >= 12 and token['h1'] >= 5 and token['volume_h24'] > 100000 and surge_prob > 0.6:
            long_candidates.append(token)
            
        # SHORT候補
        if token['h24'] <= -8 and token['h1'] <= -3 and token['volume_h24'] > 100000:
            short_candidates.append(token)

    # 上位を選出
    long_candidates = sorted(long_candidates, key=lambda x: x['surge_probability'], reverse=True)[:3]
    short_candidates = sorted(short_candidates, key=lambda x: x['h1'])[:3]
    
    # 通知したトークンをDBに記録
    with db_conn:
        for token in long_candidates + short_candidates:
            record_notification(db_conn, token['baseToken']['address'])
    
    # 市場概況
    market_overview = {
        '監視銘柄数': total_monitored,
        '上昇': len(df[df['h24'] > 0]),
        '下落': len(df[df['h24'] < 0]),
    }
    
    return long_candidates, short_candidates, [], market_overview
