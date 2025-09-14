import json
import os
import logging
from datetime import datetime, timezone, timedelta

STATE_FILE = "bot_state.json"
JST = timezone(timedelta(hours=9))  # 日本時間

class StateManager:
    def __init__(self):
        self.state = {
            "balance": 10000.0,
            "positions": {},        # {symbol: {entry_price, amount, take_profit, stop_loss}}
            "trade_history": []     # 全トレード履歴
        }
        self.load_state()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"ステート読み込み失敗: {e}")

    def save_state(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"ステート保存失敗: {e}")

    def get_balance(self):
        return self.state["balance"]

    def get_positions(self):
        return self.state["positions"]

    def open_position(self, symbol, entry_price, amount, take_profit, stop_loss):
        self.state["positions"][symbol] = {
            "entry_price": entry_price,
            "amount": amount,
            "take_profit": take_profit,
            "stop_loss": stop_loss
        }
        self.save_state()

    def close_position(self, symbol, exit_price, reason="TP/SL"):
        if symbol not in self.state["positions"]:
            return None
        pos = self.state["positions"].pop(symbol)
        pnl = (exit_price - pos["entry_price"]) * pos["amount"]
        self.state["balance"] += pnl
        record = {
            "symbol": symbol,
            "entry": pos["entry_price"],
            "exit": exit_price,
            "amount": pos["amount"],
            "pnl": pnl,
            "reason": reason,
            "timestamp": datetime.now(JST).isoformat()
        }
        self.state["trade_history"].append(record)
        self.save_state()
        return record

    def record_trade_result(self, trade):
        """外部から履歴保存したい場合に利用"""
        self.state["trade_history"].append(trade)
        self.save_state()

    def get_trade_history(self, limit=1000):
        return self.state["trade_history"][-limit:]
