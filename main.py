import logging
import threading
import schedule
import time
import requests
from flask import Flask, jsonify, request
from state_manager import StateManager
from datetime import datetime, timezone
import statistics

# === ATR計算モジュール ===
def fetch_ohlcv(symbol: str, limit=20):
    """Bitget APIから日足データを取得"""
    url = f"https://api.bitget.com/api/v2/market/history-candles?symbol={symbol}_USDT&granularity=86400&limit={limit}"
    resp = requests.get(url)
    data = resp.json()
    candles = []
    if "data" in data:
        for c in data["data"]:
            candles.append({
                "time": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4])
            })
    return list(reversed(candles))  # 時系列昇順

def calc_atr(symbol: str, period=14):
    ohlcv = fetch_ohlcv(symbol, limit=period+1)
    if len(ohlcv) < period+1:
        return None
    trs = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i]["high"]
        low = ohlcv[i]["low"]
        prev_close = ohlcv[i-1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return statistics.mean(trs[-period:])

def calc_trade_levels(entry_price, symbol, atr_mult_tp=2.0, atr_mult_sl=1.0):
    atr = calc_atr(symbol)
    if atr is None:
        return {"take_profit": entry_price * 1.02, "stop_loss": entry_price * 0.98}
    return {
        "take_profit": entry_price + atr * atr_mult_tp,
        "stop_loss": entry_price - atr * atr_mult_sl
    }

# === Flaskアプリ ===
app = Flask(__name__)
state_manager = StateManager()

# ダミー価格データ取得
def fetch_price(symbol: str):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
    resp = requests.get(url).json()
    return float(resp["price"])

# Fear & Greed Index
def fetch_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1").json()
        return resp["data"][0]
    except Exception:
        return {"value": "N/A", "value_classification": "Unknown"}

# === トレーディングサイクル ===
def run_trading_cycle():
    logging.info("=== Trading Cycle Start ===")
    symbols = ["BTC", "ETH", "SOL", "BNB"]

    for sym in symbols:
        price = fetch_price(sym)
        pos = state_manager.get_positions().get(sym)

        # --- 新規エントリー ---
        if pos is None:
            levels = calc_trade_levels(price, sym)
            size = 0.01  # ダミー
            state_manager.open_position(
                symbol=sym,
                entry_price=price,
                size=size,
                take_profit=levels["take_profit"],
                stop_loss=levels["stop_loss"]
            )
            logging.info(f"OPEN {sym}: {price}, TP={levels['take_profit']}, SL={levels['stop_loss']}")

        # --- 保有ポジション監視 ---
        else:
            tp = pos["take_profit"]
            sl = pos["stop_loss"]

            if price >= tp:
                record = state_manager.close_position(sym, price, reason="TP")
                logging.info(f"CLOSE {sym} (TP): {record}")
            elif price <= sl:
                record = state_manager.close_position(sym, price, reason="SL")
                logging.info(f"CLOSE {sym} (SL): {record}")
            else:
                logging.info(f"HOLD {sym} @ {price}, TP={tp}, SL={sl}")

# === APIエンドポイント ===
@app.route("/status", methods=["GET"])
def get_status():
    api_key = request.args.get("key")
    if api_key != "changeme":  # 認証
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify({
        "balance": state_manager.get_balance(),
        "positions": state_manager.get_positions(),
        "trade_history": state_manager.get_trade_history()[-20:],  # 直近20件
        "fear_greed": fetch_fear_greed()
    })

# === スケジューラー ===
def scheduler_thread():
    schedule.every(1).minutes.do(run_trading_cycle)
    while True:
        schedule.run_pending()
        time.sleep(1)

# === エントリーポイント ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting bot...")

    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=5000)
