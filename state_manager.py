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

        # positions: dict keyed by symbol
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
                "hedge_mode": self.hedge_mode,
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
            self.hedge_mode = data.get("hedge_mode", True)
        except Exception as e:
            logging.error("StateManager.load_state error: %s", e)

    # ---------------------------
    # snapshot
    # ---------------------------
    def update_last_snapshot(self, market_data: Dict[str, Any], balance: Any, positions: Any) -> None:
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
    # exchange sync helpers
    # ---------------------------
    def sync_balance(self, exchange) -> Optional[Dict[str, Any]]:
        try:
            bal = exchange.fetch_balance()
            logging.info("Synced balance")
            return bal
        except Exception as e:
            logging.error("sync_balance error: %s", e)
            return None

    def sync_positions(self, exchange) -> Optional[Dict[str, Any]]:
        try:
            positions_raw = []
            if hasattr(exchange, "fetch_positions"):
                positions_raw = exchange.fetch_positions() or []
            else:
                positions_raw = []

            self.positions = {}
            for pos in positions_raw:
                symbol = pos.get("symbol") or pos.get("info", {}).get("symbol") or pos.get("info", {}).get("instId")
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
    def calculate_position_size(self, exchange, market_symbol: str, usdt_balance: float, risk_pct: float, leverage: int):
        try:
            ticker = exchange.fetch_ticker(market_symbol)
            price = ticker['last']
            notional = usdt_balance * (risk_pct / 100.0) * leverage
            amount = notional / price
            logging.info(
                f"[SIZE] symbol={market_symbol}, price≈{price}, amount={amount:.6f}, "
                f"notional={notional:.2f}USDT, leverage={leverage}"
            )
            return amount
        except Exception as e:
            logging.error(f"calculate_position_size error: {e}")
            return 0.0

    def execute_entry(
        self,
        exchange,
        market_symbol: str,
        side: str,
        amount: Optional[float] = None,
        risk_pct: Optional[float] = None,
        leverage: Optional[int] = None,
        usdt_balance: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        成行エントリーを行う
        - amount を直接指定するか、risk_pct + leverage + usdt_balance から自動計算する
        """
        params = params or {}

        if self.hedge_mode:
            params["positionSide"] = "long" if side.lower() == "buy" else "short"
        else:
            params["reduceOnly"] = params.get("reduceOnly", False)

        try:
            if amount is None:
                if usdt_balance is None or risk_pct is None or leverage is None:
                    raise ValueError("amount を指定するか、usdt_balance + risk_pct + leverage を渡してください")
                amount = self.calculate_position_size(exchange, market_symbol, usdt_balance, risk_pct, leverage)

            order = exchange.create_order(
                market_symbol,
                type="market",
                side=side,
                amount=amount,
                params=params,
            )
            self.increment_entry()
            logging.info(f"[ENTRY] 注文成功: {order}")
            return order
        except Exception as e:
            logging.error(f"[ENTRY] エントリー失敗: {e}")
            return None

    def execute_exit(self, exchange, market_symbol: str, amount: float, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        params = params or {}
        try:
            details = self.get_position_details(market_symbol)
            if not details:
                logging.warning("No position details for %s, attempting simple market sell", market_symbol)
                order = exchange.create_order(symbol=market_symbol, type="market", side="sell", amount=amount, params=params)
            else:
                pos_side = details.get("side") or details.get("positionSide") or details.get("direction")
                side_to_send = "sell"
                if isinstance(pos_side, str):
                    if pos_side.lower() in ("short", "sell"):
                        side_to_send = "buy"
                    else:
                        side_to_send = "sell"
                order = exchange.create_order(symbol=market_symbol, type="market", side=side_to_send, amount=amount, params=params)

            self.remove_position(market_symbol)
            self.increment_exit()
            logging.info("Executed exit %s amount=%s", market_symbol, amount)
            return order
        except Exception as e:
            logging.error("execute_exit error for %s: %s", market_symbol, e)
            return None
