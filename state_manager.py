import json
import os
import logging
from datetime import datetime
import pytz

STATE_FILE = "bot_state.json"


class StateManager:
    """
    ボットの状態を永続化・管理するクラス。
    - ポジション情報
    - 勝率履歴
    - 資産曲線
    - 日次リターン (JST基準)
    """

    def __init__(self):
        self.state = {
            "positions": {},
            "trade_history": [],   # 個別トレード履歴
            "win_history": [],     # 勝敗履歴 (1=勝ち,0=負け)
            "balance_history": [], # 残高推移
            "daily_returns": {},   # JST日次ごとの損益
        }
        self._load_state()

    # -----------------------------
    # 内部ユーティリティ
    # -----------------------------
    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load state: {e}")

    def _save_state(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    def _get_today_jst(self):
        """JST基準の日付文字列を返す (YYYY-MM-DD)"""
        tz = pytz.timezone("Asia/Tokyo")
        return datetime.now(tz).strftime("%Y-%m-%d")

    # -----------------------------
    # ポジション関連
    # -----------------------------
    def has_position(self, symbol):
        return symbol in self.state["positions"]

    def get_position_details(self, symbol):
        return self.state["positions"].get(symbol)

    def set_position(self, symbol, is_open, details=None):
        if is_open:
            self.state["positions"][symbol] = details
        else:
            if symbol in self.state["positions"]:
                del self.state["positions"][symbol]
        self._save_state()

    def get_all_active_positions(self):
        return self.state["positions"]

    # -----------------------------
    # トレード履歴・勝率関連
    # -----------------------------
    def record_trade_result(self, symbol, result, pnl, balance):
        """
        result: "win" / "loss"
        pnl: 損益（USDT）
        balance: 決済後残高（USDT）
        """
        today = self._get_today_jst()

        # トレード履歴
        trade = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "result": result,
            "pnl": pnl,
            "balance": balance,
        }
        self.state["trade_history"].append(trade)

        # 勝敗履歴
        self.state["win_history"].append(1 if result == "win" else 0)

        # 資産推移
        self.state["balance_history"].append(
            {"timestamp": trade["timestamp"], "balance": balance}
        )

        # 日次リターン更新
        if today not in self.state["daily_returns"]:
            self.state["daily_returns"][today] = {"pnl_usdt": 0.0, "return_pct": 0.0}

        self.state["daily_returns"][today]["pnl_usdt"] += pnl

        # 前日残高を基準に日次損益率を計算
        prev_balance = balance - pnl if balance - pnl > 0 else balance
        if prev_balance > 0:
            self.state["daily_returns"][today]["return_pct"] = (
                self.state["daily_returns"][today]["pnl_usdt"] / prev_balance
            )

        self._save_state()

    def get_win_rate(self):
        if not self.state["win_history"]:
            return 0.0
        return sum(self.state["win_history"]) / len(self.state["win_history"]) * 100

    # -----------------------------
    # 状態取得
    # -----------------------------
    def get_state_snapshot(self):
        return {
            "positions": self.state["positions"],
            "trade_count": len(self.state["trade_history"]),
            "win_rate": self.get_win_rate(),
            "balance_history": self.state["balance_history"],
            "daily_returns": self.state["daily_returns"],
        }
