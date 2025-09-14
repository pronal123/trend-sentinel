import requests
import pandas as pd
import logging
import ccxt
import datetime

# Fear & Greed Index
def get_fear_greed_index():
    try:
        url = "https://api.alternative.me/fng/"
        res = requests.get(url, timeout=10).json()
        return int(res["data"][0]["value"])
    except Exception as e:
        logging.error(f"Fear & Greed Index fetch failed: {e}")
        return 50

# Coingecko トレンド銘柄
def get_coingecko_trending():
    try:
        url = "https://api.coingecko.com/api/v3/search/trending"
        res = requests.get(url, timeout=10).json()
        coins = [item["item"]["symbol"].upper() for item in res["coins"]]
        return coins[:5]  # 上位5銘柄
    except Exception as e:
        logging.error(f"Coingecko trending fetch failed: {e}")
        return []

# Bitgetから価格履歴（1分足）
def fetch_price_history(symbol: str, market_type="spot", limit=200):
    try:
        ex = ccxt.bitget({"options": {"defaultType": market_type}})
        ohlcv = ex.fetch_ohlcv(symbol, timeframe="1m", limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logging.error(f"Price history fetch failed ({symbol}): {e}")
        return pd.DataFrame()

# Bitgetから板データ
def get_orderbook(symbol: str, market_type="spot"):
    try:
        ex = ccxt.bitget({"options": {"defaultType": market_type}})
        return ex.fetch_order_book(symbol, limit=20)
    except Exception as e:
        logging.error(f"Orderbook fetch failed ({symbol}): {e}")
        return {"bids": [], "asks": []}

# TP/SL計算
def calculate_tp_sl(df, orderbook, fng_index):
    if df.empty:
        return None, None
    current_price = df["close"].iloc[-1]

    # ATR計算
    df["H-L"] = df["high"] - df["low"]
    df["H-C"] = (df["high"] - df["close"].shift()).abs()
    df["L-C"] = (df["low"] - df["close"].shift()).abs()
    df["TR"] = df[["H-L","H-C","L-C"]].max(axis=1)
    atr = df["TR"].rolling(14).mean().iloc[-1]

    sl_mult, tp_mult = 1.5, 2.5

    # 板厚で補正
    try:
        buy_liquidity = sum([o[1] for o in orderbook["bids"][:10]])
        sell_liquidity = sum([o[1] for o in orderbook["asks"][:10]])
        if buy_liquidity > sell_liquidity * 1.5:
            tp_mult += 0.5
        elif sell_liquidity > buy_liquidity * 1.5:
            sl_mult += 0.5
    except:
        pass

    # 恐怖指数補正
    if fng_index >= 70:
        tp_mult -= 0.5
    elif fng_index <= 30:
        sl_mult += 0.5

    take_profit = round(current_price + atr * tp_mult, 4)
    stop_loss = round(current_price - atr * sl_mult, 4)

    return take_profit, stop_loss

# コメント生成
def generate_comment(symbol, df, fng_index, orderbook, tp, sl):
    if df.empty:
        return f"{symbol}: データ取得失敗"

    current_price = df["close"].iloc[-1]
    change_1h = (df["close"].iloc[-1] / df["close"].iloc[-60] - 1) * 100 if len(df) > 60 else 0
    change_24h = (df["close"].iloc[-1] / df["close"].iloc[-1440] - 1) * 100 if len(df) > 1440 else 0
    rsi = calculate_rsi(df["close"])

    comment = (
        f"📊 {symbol} 市場分析\n"
        f"- 現在価格: {current_price:.4f} USDT\n"
        f"- 1時間変動: {change_1h:.2f}% | 24時間変動: {change_24h:.2f}%\n"
        f"- RSI: {rsi:.1f}\n"
        f"- 恐怖指数: {fng_index}\n"
    )
    if tp and sl:
        comment += f"🎯 利確目安: {tp} | 🛑 損切目安: {sl}\n"

    if rsi > 70:
        comment += "💡 RSI過熱 → 上昇一服の可能性あり\n"
    elif rsi < 30:
        comment += "💡 RSI低水準 → 反発狙いの局面\n"
    else:
        comment += "💡 中立圏 → 板の厚みに注目\n"

    return comment

# RSI計算
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs)).iloc[-1]

# 全体スナップショット構築
def build_market_snapshot(state_manager):
    snapshot = {}
    fng_index = get_fear_greed_index()

    # ウォッチリスト
    watchlist = ["BTC/USDT"]
    positions = state_manager.get_all_active_positions()
    for token_id in positions.keys():
        watchlist.append(f"{token_id.upper()}/USDT")
    trending = get_coingecko_trending()
    for coin in trending:
        watchlist.append(f"{coin.upper()}/USDT")

    watchlist = list(set(watchlist))

    for symbol in watchlist:
        df = fetch_price_history(symbol, market_type="spot")
        orderbook = get_orderbook(symbol, market_type="spot")
        tp, sl = calculate_tp_sl(df, orderbook, fng_index)
        comment = generate_comment(symbol, df, fng_index, orderbook, tp, sl)
        snapshot[symbol] = {
            "last_price": df["close"].iloc[-1] if not df.empty else None,
            "take_profit": tp,
            "stop_loss": sl,
            "comment": comment,
        }

    return snapshot
