import json, logging
from pathlib import Path
from datetime import datetime, timezone

class StateManager:
    def __init__(self, filename="bot_state.json"):
        self.file = Path(filename)
        self.state = {
            "positions": {},          # symbol -> details
            "trade_history": [],     # list of {"time":..., "symbol":..., "result":"win"/"loss", "pnl":...}
            "last_notified": {},     # symbol -> iso time string (duplicate suppression)
            "balance": 10000.0
        }
        self._load()

    def _load(self):
        if self.file.exists():
            try:
                self.state = json.loads(self.file.read_text())
                logging.info("Loaded bot state")
            except Exception as e:
                logging.error(f"Failed load state: {e}")

    def save_state(self):
        try:
            self.file.write_text(json.dumps(self.state, indent=2))
        except Exception as e:
            logging.error(f"Failed save state: {e}")

    # positions
    def set_position(self, symbol, details):
        self.state["positions"][symbol] = details
        self.save_state()

    def remove_position(self, symbol):
        if symbol in self.state["positions"]:
            del self.state["positions"][symbol]
            self.save_state()

    def get_positions(self):
        return self.state.get("positions", {})

    # trade history
    def record_trade_result(self, symbol, result, pnl=None):
        rec = {"time": datetime.now(timezone.utc).isoformat(), "symbol": symbol, "result": result}
        if pnl is not None: rec["pnl"] = pnl
        self.state.setdefault("trade_history", []).append(rec)
        self.save_state()

    def get_win_rate(self):
        hist = self.state.get("trade_history", [])
        if not hist: return 0.0
        wins = sum(1 for h in hist if h.get("result") == "win")
        return round(wins / len(hist) * 100, 2)

    def get_win_rate_history(self):
        # return list of (time, rate) computed cumulatively
        hist = self.state.get("trade_history", [])
        out = []
        wins = 0
        for i, h in enumerate(hist, start=1):
            if h.get("result") == "win": wins += 1
            out.append({"time": h["time"], "value": round(wins / i * 100, 2)})
        return out

    # dedupe notifications: store last notified ISO string
    def mark_notified(self, symbol):
        self.state.setdefault("last_notified", {})[symbol] = datetime.now(timezone.utc).isoformat()
        self.save_state()

    def was_notified_recently(self, symbol, seconds=6*3600):
        t = self.state.get("last_notified", {}).get(symbol)
        if not t: return False
        dt = datetime.fromisoformat(t)
        return (datetime.now(timezone.utc) - dt).total_seconds() < seconds

    # balance
    def get_balance(self):
        return self.state.get("balance", 0.0)

    def update_balance(self, val):
        self.state["balance"] = val
        self.save_state()
