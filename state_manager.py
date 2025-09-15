import logging
import statistics
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class StateManager:
    """
    Trend Sentinel - State Manager
    ・トレード履歴管理
    ・残高管理
    ・ポジション状態管理
    ・統計値計算（WinRate, ProfitFactor, Sharpe, DDなど）
    ・AI風コメント生成
    """

    def __init__(self, initial_balance: float = 10000.0):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []

    # =========================================================
    # 残高・ポジション管理
    # =========================================================
    def update_balance(self, amount: float):
        self.balance += amount
        logger.info(f"[Balance Updated] New balance={self.balance:.2f}")

    def get_balance(self) -> float:
        return self.balance

    def add_position(self, symbol: str, side: str, size: float, entry: float,
                     tp: float = None, sl: float = None):
        self.positions[symbol] = {
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "timestamp": datetime.utcnow().isoformat()
        }
        logger.info(f"[Position Opened] {symbol} {side} {size}@{entry}, TP={tp}, SL={sl}")

    def close_position(self, symbol: str, exit_price: float):
        if symbol not in self.positions:
            return None

        pos = self.positions.pop(symbol)
        pnl = (exit_price - pos["entry"]) * pos["size"]
        if pos["side"].lower() == "short":
            pnl *= -1

        self.update_balance(pnl)

        trade = {
            "symbol": symbol,
            "side": pos["side"],
            "size": pos["size"],
            "entry": pos["entry"],
            "exit": exit_price,
            "pnl": pnl,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.trade_history.append(trade)
        logger.info(f"[Position Closed] {symbol} exit={exit_price}, PnL={pnl:.2f}")
        return trade

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.positions

    def get_trade_history(self) -> List[Dict[str, Any]]:
        return self.trade_history

    # =========================================================
    # 統計系メトリクス
    # =========================================================
    def get_win_rate(self, lookback: int = 1000) -> float:
        trades = self.trade_history[-lookback:]
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t["pnl"] > 0)
        return wins / len(trades)

    def get_profit_factor(self, lookback: int = 1000) -> float:
        trades = self.trade_history[-lookback:]
        gains = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        losses = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
        return gains / losses if losses > 0 else float("inf")

    def get_sharpe_ratio(self, lookback: int = 1000) -> float:
        trades = self.trade_history[-lookback:]
        returns = [t["pnl"] / self.initial_balance for t in trades]
        if len(returns) < 2:
            return 0.0
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        return mean_r / std_r if std_r > 0 else 0.0

    def get_max_drawdown(self, lookback: int = 1000) -> float:
        trades = self.trade_history[-lookback:]
        equity_curve = []
        equity = 0
        max_equity = 0
        max_dd = 0
        for t in trades:
            equity += t["pnl"]
            max_equity = max(max_equity, equity)
            dd = (equity - max_equity)
            max_dd = min(max_dd, dd)
        return max_dd

    # =========================================================
    # AI風コメント生成
    # =========================================================
    def generate_ai_comment(self, symbol: str, orderbook: Dict[str, Any],
                            ticker: Dict[str, Any], atr: float,
                            fear_greed: str = "Unknown") -> str:
        """AI風コメントを返す（板厚・ATR・市場心理・チャート分析など）"""
        bid_depth = sum([b[1] for b in orderbook.get("bids", [])[:5]]) if orderbook else 0
        ask_depth = sum([a[1] for a in orderbook.get("asks", [])[:5]]) if orderbook else 0

        imbalance = "Buyers strong" if bid_depth > ask_depth else "Sellers strong"

        comment = (
            f"[AI Market View] {symbol}\n"
            f"・市場心理(Fear&Greed): {fear_greed}\n"
            f"・板厚分析: Bid={bid_depth:.2f}, Ask={ask_depth:.2f}, ({imbalance})\n"
            f"・ATR(Volatility): {atr:.2f}\n"
            f"・最新価格: {ticker.get('last', 'N/A')}\n"
            f"・チャート傾向: {'上昇' if ticker.get('change', 0) > 0 else '下落'}\n"
        )
        return comment

    # =========================================================
    # 総合スコアリング
    # =========================================================
    def get_composite_score(self, lookback: int = 1000) -> float:
        wr = self.get_win_rate(lookback)
        pf = self.get_profit_factor(lookback)
        sharpe = self.get_sharpe_ratio(lookback)

        score = 0
        if wr > 0.5:
            score += 1
        if pf > 1.0:
            score += 1
        if sharpe > 1.0:
            score += 1

        return score
