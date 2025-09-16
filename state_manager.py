# state_manager.py
import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

JST = timezone(timedelta(hours=9))

class StateManager:
    def __init__(self, state_file: str = "state.json", notification_interval: int = 21600):
        self.state_file = state_file
        self.notification_interval = notification_interval

        # 両方向モードを前提に運用するフラグ
        self.hedge_mode: bool = True

        # last snapshot of market / account / positions
        self.last_snapshot: Optional[Dict[str, Any]] = None

        # tokens already notified (for notifications throttling, optional)
        self.notified_tokens: Dict[str, Any] = {}

        # positions: dict keyed by symbol (e.g. "BTC/USDT" or "BTCUSDT" depending on your normalization)
        # value: {"in_position": bool, "details": { ... }}
        self.positions: Dict[str, Dict[str, Any]] = {}

        # pending signals (before execution)
        self.pending_signals: Dict[str, Dict[str, Any]] = {}

        # trade / performance tracking
        self.trade_history: List[Dict[str, Any]] = []
        self.entry_count: int = 0
        self.exit_count: int = 0
        self.realized_pnl: List[Dict[str, Any]] = []  # [{timestamp: str, pnl: float}]

        # load persisted state if exists
        self.load_state()

    # ---------------------------
    # persistence
    # ---------------------------
    def save_state(self) -> None:
        try:
            payload = {
                "notified_tokens": self.notified_tokens,
                "positions": self.positions,
                "pending_signals": self.pending_signals,
                "trade_history": self.trade_history,
                "entry_count": self.entry_count,
                "exit_count": self.exit_count,
                "realized_pnl": self.realized_pnl,
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error("StateManager.save_state error: %s", e)

    def load_state(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.notified_tokens = data.get("notified_tokens", {})
            self.positions = data.get("positions", {})
            self.pending_signals = data.get("pending_signals", {})
            self.trade_history = data.get("trade_history", [])
            self.entry_count = data.get("entry_count", 0)
            self.exit_count = data.get("exit_count", 0)
            self.realized_pnl = data.get("realized_pnl", [])
        except Exception as e:
            logging.error("StateManager.load_state error: %s", e)

    # ---------------------------
    # snapshot
    # ---------------------------
    def update_last_snapshot(self, market_data: Dict[str, Any], balance: Any, positions: Any) -> None:
        """保存用の最新スナップショット"""
        self.last_snapshot = {
            "market_data": market_data,
            "balance": balance,
            "positions": positions,
            "timestamp": int(time.time())
        }

    def get_last_snapshot(self) -> Optional[Dict[str, Any]]:
        return self.last_snapshot

    # ---------------------------
    # pending signals
    # ---------------------------
    def add_pending_signal(self, token_id: str, details: Dict[str, Any]) -> None:
        self.pending_signals[token_id] = details
        self.save_state()
        logging.info("Added pending signal %s", token_id)

    def get_and_clear_pending_signals(self) -> Dict[str, Dict[str, Any]]:
        pending = self.pending_signals.copy()
        self.pending_signals = {}
        self.save_state()
        return pending

    # ---------------------------
    # positions management
    # ---------------------------
    def has_position(self, token_id: str) -> bool:
        return bool(self.positions.get(token_id, {}).get("in_position", False))

    def set_position(self, token_id: str, in_position: bool, details: Optional[Dict[str, Any]] = None) -> None:
        self.positions[token_id] = {"in_position": bool(in_position), "details": details}
        self.save_state()
        logging.info("Position %s -> in_position=%s", token_id, in_position)

    def remove_position(self, token_id: str) -> None:
        if token_id in self.positions:
            del self.positions[token_id]
            self.save_state()
            logging.info("Removed position %s", token_id)

    def get_position_details(self, token_id: str) -> Optional[Dict[str, Any]]:
        return self.positions.get(token_id, {}).get("details")

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        return {t: v["details"] for t, v in self.positions.items() if v.get("in_position")}

    def get_open_tokens(self) -> List[str]:
        return [t for t, v in self.positions.items() if v.get("in_position")]

    # ---------------------------
    # trade statistics
    # ---------------------------
    def record_trade_result(self, token_id: str, result: str) -> None:
        """result: 'win' or 'loss' (optionally other labels)"""
        if result not in ("win", "loss"):
            logging.warning("record_trade_result: unexpected result %s", result)
        self.trade_history.append({"token_id": token_id, "result": result, "timestamp": int(time.time())})
        self.save_state()
        logging.info("Recorded trade result %s -> %s", token_id, result)

    def get_win_rate(self) -> float:
        if not self.trade_history:
            return 0.0
        wins = sum(1 for t in self.trade_history if t.get("result") == "win")
        return (wins / len(self.trade_history)) * 100.0

    def increment_entry(self) -> None:
        self.entry_count += 1
        self.save_state()

    def increment_exit(self) -> None:
        self.exit_count += 1
        self.save_state()

    def get_trade_counts(self) -> (int, int):
        return self.entry_count, self.exit_count

    def record_realized_pnl(self, pnl_usd: float) -> None:
        now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        self.realized_pnl.append({"timestamp": now, "pnl": float(pnl_usd)})
        self.save_state()

    def get_daily_pnl(self) -> float:
        today = datetime.now(JST).strftime("%Y-%m-%d")
        return sum(r["pnl"] for r in self.realized_pnl if r["timestamp"].startswith(today))

    # ---------------------------
    # exchange sync helpers (ccxt exchange expected)
    # ---------------------------
    def sync_balance(self, exchange) -> Optional[Dict[str, Any]]:
        """exchange.fetch_balance() を呼んで残高を取得して返す（例外はログ）"""
        try:
            bal = exchange.fetch_balance()
            logging.info("Synced balance")
            return bal
        except Exception as e:
            logging.error("sync_balance error: %s", e)
            return None

    def sync_positions(self, exchange) -> Optional[Dict[str, Any]]:
        """
        exchange.fetch_positions() を呼び出して internal positions を上書きします。
        注意: exchange によって返却形式が異なるため、ここは適宜調整してください。
        """
        try:
            positions_raw = []
            # try common fetch_positions, otherwise fallback to fetch_balance / parse open positions
            if hasattr(exchange, "fetch_positions"):
                positions_raw = exchange.fetch_positions() or []
            else:
                # 一部の取引所は fetch_positions を持たない -> fetch_balance からポジション情報を作る必要あり（省略）
                positions_raw = []

            # normalize into self.positions
            self.positions = {}
            for pos in positions_raw:
                # pos may be dict with 'symbol' or 'info'
                symbol = pos.get("symbol") or pos.get("info", {}).get("symbol") or pos.get("info", {}).get("instId")
                # try to determine if there's an open position (取引所依存)
                # prioritize common keys:
                contracts = pos.get("contracts") or pos.get("size") or pos.get("positionAmt") or pos.get("amount") or 0
                in_pos = False
                try:
                    in_pos = float(contracts) != 0.0
                except Exception:
                    in_pos = bool(contracts)
                self.positions[symbol] = {"in_position": in_pos, "details": pos if in_pos else None}

            self.save_state()
            logging.info("Synced positions: %d entries", len(self.positions))
            return self.positions
        except Exception as e:
            logging.error("sync_positions error: %s", e)
            return None

    # ---------------------------
    # simple order execution helpers
    # ---------------------------
    def execute_entry(
        self,
        exchange,
        market_symbol: str,
        side: str,
        risk_pct: float = 1.0,
        leverage: int = 1,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        残高とリスク割合に基づいて数量を自動計算し、市場成行でエントリー
        """
        try:
            # 残高取得（USDT基準）
            balance = exchange.fetch_balance()
            usdt_balance = balance['total'].get('USDT', 0)
            if usdt_balance <= 0:
                logging.error("残高が不足しているため発注できません")
                return None

            # 現在価格取得
            ticker = exchange.fetch_ticker(market_symbol)
            price = ticker['last']

            # 注文金額 = 残高 × (リスク割合 / 100) × レバレッジ
            notional = usdt_balance * (risk_pct / 100.0) * leverage

            # 数量計算（例: BTC数量）
            amount = notional / price

            logging.info(
                f"[ENTRY] symbol={market_symbol}, side={side}, "
                f"price≈{price}, amount={amount:.6f}, "
                f"notional={notional:.2f}USDT, leverage={leverage}"
            )

            # レバレッジ設定（Bitget専用）
            try:
                exchange.set_leverage(leverage, symbol=market_symbol)
            except Exception as e:
                logging.warning(f"レバレッジ設定失敗: {e}")

            # 成行注文
            order = exchange.create_order(
                symbol=market_symbol,
                type="market",
                side=side,
                amount=amount,
                params=params or {}
            )

            # StateManagerにポジション登録
            self.set_position(
                market_symbol,
                status=True,
                details={
                    "side": side,
                    "amount": amount,
                    "entry_price": price,
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "leverage": leverage
                }
            )

            return order

        except Exception as e:
            logging.error(f"エントリー失敗: {e}")
            return None

    def execute_exit(self, exchange, market_symbol: str, amount: float, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        市場成行で決済（全量 or 部分）を行うラッパー。
        - amount: 決済数量（asset単位 or contracts）
        """
        params = params or {}
        try:
            # 決済側のサイドは現在のポジションに依存するが、ここではユーザ側で side を決めさせる代わりに
            # 'close' を params に渡す方式もある。シンプルに market sell/buy を発注する例:
            # まずポジション詳細を参照
            details = self.get_position_details(market_symbol)
            if not details:
                logging.warning("No position details for %s, attempting simple market sell", market_symbol)
                # 決済サイドはポジションの建玉に応じて変えるはずだが、簡便のため 'sell' を投げます
                order = exchange.create_order(symbol=market_symbol, type="market", side="sell", amount=amount, params=params)
            else:
                # try to detect which side to issue as close: if pos has 'side' or 'positionSide'
                pos_side = details.get("side") or details.get("positionSide") or details.get("direction")
                # if pos_side indicates 'long'/'buy' -> close with sell
                side_to_send = "sell"
                if isinstance(pos_side, str):
                    if pos_side.lower() in ("short", "sell"):
                        side_to_send = "buy"
                    else:
                        side_to_send = "sell"
                order = exchange.create_order(symbol=market_symbol, type="market", side=side_to_send, amount=amount, params=params)

            # update internal state
            self.remove_position(market_symbol)
            self.increment_exit()
            logging.info("Executed exit %s amount=%s", market_symbol, amount)
            return order
        except Exception as e:
            logging.error("execute_exit error for %s: %s", market_symbol, e)
            return None
