import logging
from datetime import datetime
from typing import Dict, Any, Optional


class StateManager:
    """
    システム全体の状態を管理するクラス
    - 残高
    - 建玉
    - トレード履歴
    - サイクルごとのスナップショット
    - 勝率や統計情報
    """

    def __init__(self):
        self.balance: float = 0.0
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.last_snapshot: Optional[Dict[str, Any]] = None
        self.trade_history: list[Dict[str, Any]] = []
        self.stats: Dict[str, Any] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_loss": 0.0,
        }

    # ==============================
    # Balance 管理
    # ==============================
    def update_balance(self, new_balance: float):
        self.balance = new_balance
        logging.info(f"[STATE] Balance updated: {new_balance}")

    def get_balance(self) -> float:
        return self.balance

    # ==============================
    # Positions 管理
    # ==============================
    def update_position(self, symbol: str, position: Dict[str, Any]):
        """建玉を更新"""
        self.positions[symbol] = position
        logging.info(f"[STATE] Position updated for {symbol}: {position}")

    def remove_position(self, symbol: str):
        """建玉を削除"""
        if symbol in self.positions:
            del self.positions[symbol]
            logging.info(f"[STATE] Position removed for {symbol}")

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.positions

    # ==============================
    # Trade History 管理
    # ==============================
    def record_trade(self, trade: Dict[str, Any]):
        """
        トレード履歴を記録
        trade = {
            "symbol": str,
            "side": "long" | "short",
            "entry_price": float,
            "exit_price": float,
            "pnl": float
        }
        """
        trade["timestamp"] = datetime.utcnow().isoformat()
        self.trade_history.append(trade)

        # Stats 更新
        self.stats["total_trades"] += 1
        self.stats["profit_loss"] += trade.get("pnl", 0.0)
        if trade.get("pnl", 0.0) > 0:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1

        if self.stats["total_trades"] > 0:
            self.stats["win_rate"] = (
                self.stats["wins"] / self.stats["total_trades"]
            )

        logging.info(f"[STATE] Trade recorded: {trade}")

    def get_trade_history(self) -> list[Dict[str, Any]]:
        return self.trade_history

    # ==============================
    # Snapshot 管理
    # ==============================
    def update_last_snapshot(self, snapshot: Dict[str, Any]):
        """
        各サイクルのスナップショットを保存
        snapshot = {
            "timestamp": str,
            "symbols": list[str],
            "analysis": dict,
            "positions": dict
        }
        """
        self.last_snapshot = snapshot
        logging.debug("[STATE] Last snapshot updated")

    def get_last_snapshot(self) -> Optional[Dict[str, Any]]:
        return self.last_snapshot

    # ==============================
    # Stats 管理
    # ==============================
    def get_win_rate(self) -> float:
        return self.stats.get("win_rate", 0.0)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "balance": self.balance,
            "open_positions": len(self.positions),
            "trade_count": self.stats["total_trades"],
            "wins": self.stats["wins"],
            "losses": self.stats["losses"],
            "win_rate": self.stats["win_rate"],
            "profit_loss": self.stats["profit_loss"],
        }
