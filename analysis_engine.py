# analysis_engine.py
import pandas as pd

class AnalysisEngine:
    def run_analysis(self, df):
        if df.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}

        long_cond = (df['price_change_24h'] >= 12) & (df['price_change_1h'] >= 5) & (df['volume_change_24h'] >= 150)
        long_df = df[long_cond].sort_values(by='price_change_1h', ascending=False)

        short_cond = (df['price_change_24h'] <= -8) & (df['price_change_1h'] <= -3) & (df['volume_change_24h'] >= 200)
        short_df = df[short_cond].sort_values(by='price_change_1h', ascending=True)

        spike_cond = (df['price_change_1h'] >= 8) & (df['volume_15m_multiple'] >= 3)
        spike_df = df[spike_cond].sort_values(by='price_change_1h', ascending=False)

        summary = {
            'total_monitored': len(df), 'gainers': len(df[df['price_change_24h'] > 0]),
            'losers': len(df[df['price_change_24h'] < 0]), 'volume_spikes': len(df[df['volume_change_24h'] >= 150])
        }
        return long_df, short_df, spike_df, summary
