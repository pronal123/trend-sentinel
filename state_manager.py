import json
import os
import logging
from datetime import datetime

STATE_FILE = "state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"positions": {}, "history": [], "balance": 10000.0}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_balance():
    state = load_state()
    return state.get("balance", 0)

def update_balance(amount):
    state = load_state()
    state["balance"] = state.get("balance", 0) + amount
    save_state(state)

def add_position(symbol, side, size, entry_price, tp_levels, sl):
    state = load_state()
    state["positions"][symbol] = {
        "side": side,
        "size": size,
        "entry_price": entry_price,
        "tp_levels": tp_levels,
        "sl": sl,
        "opened_at": datetime.utcnow().isoformat(),
    }
    save_state(state)

def close_position(symbol, exit_price, reason):
    state = load_state()
    if symbol not in state["positions"]:
        logging.warning(f"No position to close for {symbol}")
        return None

    pos = state["positions"].pop(symbol)
    side = pos["side"]
    size = pos["size"]
    entry_price = pos["entry_price"]

    # PnL calculation (long vs short)
    pnl = 0
    if side == "long":
        pnl = (exit_price - entry_price) * size
    elif side == "short":
        pnl = (entry_price - exit_price) * size

    # Apply fees and slippage
    fee = abs(entry_price * size) * 0.0006
    pnl_after_fee = pnl - fee

    # Update balance
    state["balance"] = state.get("balance", 0) + pnl_after_fee

    # Record history
    state["history"].append({
        "symbol": symbol,
        "side": side,
        "size": size,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": pnl_after_fee,
        "reason": reason,
        "opened_at": pos["opened_at"],
        "closed_at": datetime.utcnow().isoformat(),
    })

    save_state(state)
    return pnl_after_fee

def get_positions():
    return load_state().get("positions", {})

def get_history():
    return load_state().get("history", [])
