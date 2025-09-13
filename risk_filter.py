# risk_filter.py
import logging

def filter_risky_tokens(df):
    initial_count = len(df)
    # TODO: ここにハニーポット/未検証/高税率トークンを除外するAPI呼び出しを実装
    # 例: safe_tokens = check_safety_api(df['id'].tolist())
    # 以下はダミー実装として'scam'というシンボルを持つものを除外
    df_filtered = df[~df['symbol'].str.contains('scam', case=False)]
    
    removed_count = initial_count - len(df_filtered)
    if removed_count > 0:
        logging.info(f"Filtered out {removed_count} risky tokens.")
    return df_filtered
