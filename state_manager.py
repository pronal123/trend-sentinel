import json
import os
import datetime
import logging


class StateManager:
    def __init__(self, state_file="bot_state.json"):
        self.state_file = state_file
        self.state = {
            "balance": 10000.0,
            "positions": {},
            "summary": {},
            "balance_history": [],
            "daily_returns": {},
            "trade_history": []  # 直近1000件保持
        }
        self.load_state()

    # -------------------------
    # 状態ロード/セーブ
    # -------------------------
    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load state: {e}")

    def save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    # -------------------------
    # トレード結果記録
    # -------------------------
    def record_trade_result(self, symbol, side, pnl, balance):
        now = datetime.datetime.now().isoformat()

        trade = {
            "timestamp": now,
            "symbol": symbol,
            "side": side,
            "pnl": float(pnl),
            "balance": float(balance),
            "return_pct": (pnl / balance * 100) if balance > 0 else 0.0,
        }

        # trade_history に追加（直近1000件）
        self.state.setdefault("trade_history", [])
        self.state["trade_history"].append(trade)
        if len(self.state["trade_history"]) > 1000:
            self.state["trade_history"] = self.state["trade_history"][-1000:]

        # balance と履歴
        self.state["balance"] = float(balance)
        self.state.setdefault("balance_history", [])
        self.state["balance_history"].append({
            "timestamp": now,
            "balance": float(balance)
        })
        if len(self.state["balance_history"]) > 2000:
            self.state["balance_history"] = self.state["balance_history"][-2000:]

        self.save_state()

    # -------------------------
    # スナップショット取得
    # -------------------------
    def get_state_snapshot(self):
        return self.state
