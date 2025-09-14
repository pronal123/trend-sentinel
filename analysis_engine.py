# simple rule-based analyzer per your spec
import logging
from config import LONG_RULE, SHORT_RULE, SPIKE_RULE, CANDIDATE_POOL_SIZE

class AnalysisEngine:
    def __init__(self):
        pass

    def analyze_universe(self, market_df_list):
        """
        input: list of dict per token:
          { "symbol": "ETH/USDT", "24h": float, "1h": float, "vol_24h_pct": float, "vol_15m_mult": float }
        returns: long_candidates (sorted), short_candidates, spikes
        Each element: dict with keys symbol, 24h, 1h, vol_pct, reason
        """
        long_candidates, short_candidates, spikes = [], [], []
        for t in market_df_list:
            s = t.get("symbol")
            v24 = t.get("24h", 0.0); v1 = t.get("1h", 0.0); vol_pct = t.get("vol_pct", 0.0)
            vol15_mult = t.get("vol_15m_mult", 1.0)
            # LONG rule
            if v24 >= LONG_RULE["24h"] and v1 >= LONG_RULE["1h"] and vol_pct >= LONG_RULE["volume_pct"]:
                long_candidates.append({"symbol": s, "24h": v24, "1h": v1, "vol_pct": vol_pct, "reason": "24h+ & 1h+ & vol surge"})
            # SHORT rule
            if v24 <= SHORT_RULE["24h"] and v1 <= SHORT_RULE["1h"] and vol_pct >= SHORT_RULE["volume_pct"]:
                short_candidates.append({"symbol": s, "24h": v24, "1h": v1, "vol_pct": vol_pct, "reason": "24h- & 1h- & vol surge"})
            # spike rule
            if v1 >= SPIKE_RULE["1h"] and vol15_mult >= SPIKE_RULE["15m_volume_mult"]:
                spikes.append({"symbol": s, "24h": v24, "1h": v1, "vol_pct": vol_pct, "reason": "1h spike + 15m vol x"})
        # sort by priority (e.g., 24h desc for long, asc for short)
        long_candidates = sorted(long_candidates, key=lambda x: x["24h"], reverse=True)[:3]
        short_candidates = sorted(short_candidates, key=lambda x: x["24h"])[:3]
        spikes = sorted(spikes, key=lambda x: x["1h"], reverse=True)[:4]
        return long_candidates, short_candidates, spikes
