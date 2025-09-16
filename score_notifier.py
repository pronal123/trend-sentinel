import os
import time
import schedule
import pandas as pd
import ccxt
import requests

from main import generate_ai_comment, fetch_top_symbols, fetch_ohlcv, calc_atr_from_ohlcv, fetch_orderbook, fetch_fear_and_greed, symbol_market_ccxt

# 環境変数
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ccxt_client = ccxt.bitget({"enableRateLimit": True})

def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram送信エラー:", e)

def analyze_market(scores_df):
    """市場全体のコメントを生成"""
    avg_score = scores_df["score"].mean()
    comment = "市場分析コメント:\n"

    if avg_score >= 65:
        comment += "🚀 強気優勢"
    elif avg_score <= 35:
        comment += "⚠️ 弱気傾向"
    else:
        comment += "😐 中立レンジ"

    return comment

def run_score_cycle():
    try:
        fg = fetch_fear_and_greed()
        top20 = fetch_top_symbols(limit=20)

        results = []
        for symbol in top20:
            try:
                # 価格
                ticker = ccxt_client.fetch_ticker(symbol_market_ccxt(symbol))
                price = ticker.get("last") or ticker.get("close")
                # ATR
                atr = calc_atr_from_ohlcv(fetch_ohlcv(symbol, timeframe="1d", limit=20))
                # 板
                ob = fetch_orderbook(symbol, depth=50)
                # コメント＋スコア
                comment, score = generate_ai_comment(symbol, price, atr, ob, fg, fetch_ohlcv(symbol, timeframe="1m", limit=200))
                results.append({"symbol": symbol, "score": score})
            except Exception as e:
                print(f"{symbol} 取得失敗: {e}")

        df = pd.DataFrame(results).sort_values("score", ascending=False).head(3)

        # メッセージ生成
        msg = "📊 Bitget TOP20 スコア上位3\n"
        for _, row in df.iterrows():
            msg += f"{row['symbol']}: スコア={row['score']:.1f}\n"

        # 市場コメント
        msg += "\n" + analyze_market(pd.DataFrame(results))

        send_telegram_message(msg)

    except Exception as e:
        send_telegram_message(f"⚠️ スコア通知エラー: {str(e)}")

# スケジュール（30分ごと）
schedule.every(30).minutes.do(run_score_cycle)

if __name__ == "__main__":
    send_telegram_message("✅ スコア通知BOTが起動しました")
    while True:
        schedule.run_pending()
        time.sleep(1)
