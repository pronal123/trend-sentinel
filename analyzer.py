import asyncio
import logging
import ccxt
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Project modules
from config import (
    EXCHANGE_NAME, EXCHANGE_API_KEY, EXCHANGE_API_SECRET, EXCHANGE_API_PASSPHRASE,
    MORALIS_API_KEY, PROXY_URL,
    ADX_THRESHOLD, ML_LABEL_LOOKBACK_HOURS, ML_PRICE_GROWTH_THRESHOLD,
    NOTIFICATION_COOLDOWN_HOURS
)
# ✅ 修正: 以下の行を削除またはコメントアウト
# from database import check_if_recently_notified, record_notification 
from trader import execute_trade_logic, exchange # trader.exchangeはinitialize_exchangeで設定されたもの
from ml_model import load_model, preprocess_data, make_prediction
from notifier import format_and_send_notification # notifierから通知関連関数をインポート


# ロギング設定 (main.pyでbasicConfigが設定されているため、ここではハンドラ追加のみ)
logger = logging.getLogger(__name__)

# モラルAPIのセットアップ (aiohttpを使用しない場合はrequestsに置き換え可能)
import httpx # aiohttpの代わりにhttpxを使用

MORALIS_API_URL = "https://deep-index.moralis.io/api/v2"

# --- データ取得関数 ---
async def fetch_top_tokens(limit=10):
    """Moralis APIからトップトークンをフェッチする"""
    headers = {"X-API-KEY": MORALIS_API_KEY}
    params = {"limit": limit}
    
    # httpxのAsyncClientを使用
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MORALIS_API_URL}/top-tokens", headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            # 応答構造に基づいてトークンリストを抽出
            tokens = [
                {
                    'symbol': item['token']['symbol'],
                    'address': item['token']['tokenAddress'],
                    'priceUsd': float(item['price']['value']) / (10 ** float(item['price']['decimals'])),
                    'priceDecimals': item['price']['decimals'],
                    'usdValue': item['usdValue']
                } for item in data['topSelling']
            ]
            logger.info(f"Fetched {len(tokens)} top tokens from Moralis.")
            return tokens
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching top tokens: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error fetching top tokens: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching top tokens: {e}", exc_info=True)
    return []

async def fetch_ohlcv_data(token_address, timeframe='1h', limit=30):
    """DexScreener APIからOHLCVデータをフェッチする"""
    # DexScreenerのAPIはペアアドレスが必要。トークンアドレスからペアを探す必要があるが、
    # この例では簡略化のため、直接トークンアドレスをペアとして試行。
    # 実際のDEX Screener APIは 'pair_address' が必要です。
    # 正しい実装では、まず /pairs/<chain>/<token_address> でペアを見つけるべきです。
    # 例: https://api.dexscreener.com/latest/dex/pairs/ethereum/0x...
    # そしてその応答から pairAddress を抽出して ohlcv に使う。
    
    # 簡略化のため、ここでは直接トークンアドレスをペアとして試行
    url = f"https://api.dexscreener.com/latest/dex/ohlcv/pairs/{token_address}?res={timeframe}&limit={limit}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            # DexScreenerのOHLCVデータは 'ohlcv' キーの下にあると仮定
            if data and 'ohlcv' in data and data['ohlcv']:
                df = pd.DataFrame(data['ohlcv'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.set_index('timestamp')
                df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
                return df
            else:
                logger.warning(f"No OHLCV data found for {token_address} ({timeframe}) on DexScreener.")
                return pd.DataFrame() # 空のDataFrameを返す
        except httpx.HTTPStatusError as e:
            logger.warning(f"Failed to fetch OHLCV data for {token_address} ({timeframe}): {e.response.status_code}, message='{e.response.reason_phrase}', url='{url}'")
        except httpx.RequestError as e:
            logger.warning(f"Request error fetching OHLCV data for {token_address} ({timeframe}): {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching OHLCV data for {token_address} ({timeframe}): {e}", exc_info=True)
    return pd.DataFrame()

# --- テクニカル指標の計算 (簡易版) ---
def calculate_indicators(df):
    """OHLCVデータからテクニカル指標を計算する (ADXと単純な長期トレンド)"""
    if df.empty or len(df) < 20: # ADX計算に十分なデータがない場合
        return {}

    # ADX (簡易版): 既存のta-libなどを使用するとより正確
    # ここではADXの計算を省略し、ダミー値を返すか、よりシンプルなトレンド指標を使用
    # ta-libをインストールしている場合:
    # import talib
    # df['plus_di'] = talib.PLUS_DI(df['high'], df['low'], df['close'], timeperiod=14)
    # df['minus_di'] = talib.MINUS_DI(df['high'], df['low'], df['close'], timeperiod=14)
    # df['adx_14'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
    
    # ta-libなしの代替 (より簡易的)
    df['ma_short'] = df['close'].rolling(window=10).mean()
    df['ma_long'] = df['close'].rolling(window=50).mean()

    indicators = {
        'adx_14': 30.0, # ダミー値、またはより複雑な計算が必要
        'long_term_trend': 'UP' if df['close'].iloc[-1] > df['ma_long'].iloc[-1] else 'DOWN'
    }
    
    # 最後の行のADX値があればそれを使う、なければダミー
    # if 'adx_14' in df and not df['adx_14'].empty:
    #     indicators['adx_14'] = df['adx_14'].iloc[-1]

    return indicators

# --- 分析と通知のメインロジック ---
async def analyze_and_notify(bot):
    """
    トップトークンを分析し、AI予測と戦略に基づいて通知・取引を実行する
    """
    logger.info("Starting analysis cycle...")
    
    # 既存のAIモデルをロード
    model = load_model()
    if model is None:
        logger.error("AI model not loaded. Skipping analysis.")
        return

    tokens = await fetch_top_tokens(limit=50) # より多くのトークンをフェッチ
    long_signals = []
    short_signals = []
    all_indicators = {} # 全てのトークンの詳細指標を保存

    for token in tokens:
        symbol = token['symbol']
        token_address = token['address']
        current_price = token['priceUsd']

        # ML予測用データ（過去1時間足）
        ohlcv_1h_df = await fetch_ohlcv_data(token_address, timeframe='60', limit=ML_LABEL_LOOKBACK_HOURS + 1) # ラベル計算用に過去のデータも必要

        if ohlcv_1h_df.empty or len(ohlcv_1h_df) < ML_LABEL_LOOKBACK_HOURS + 1:
            logger.warning(f"Not enough 1h OHLCV data for ML prediction for {symbol}. Skipping ML analysis.")
            continue
        
        # 予測のための特徴量生成
        processed_data = preprocess_data(ohlcv_1h_df)
        if processed_data.empty:
            logger.warning(f"Preprocessing failed for {symbol}. Skipping ML prediction.")
            continue

        # AI予測の実行
        prediction, probabilities = make_prediction(model, processed_data)
        surge_prob = probabilities[0][1] if probabilities is not None else 0 # 'up'の確率
        dump_prob = probabilities[0][0] if probabilities is not None else 0 # 'down'の確率

        token_info = {
            'baseToken': {'symbol': symbol, 'address': token_address},
            'priceUsd': current_price,
            'surge_probability': surge_prob,
            'dump_probability': dump_prob
        }

        # --- 長期トレンド・ADXなどの詳細指標計算（1日足を使用） ---
        ohlcv_1d_df = await fetch_ohlcv_data(token_address, timeframe='1D', limit=30)
        detailed_indicators = calculate_indicators(ohlcv_1d_df)
        all_indicators[token_address] = detailed_indicators # 後でtraderに渡すために保存

        # シグナルリストに追加 (AIの確信度がconfigの閾値を超えている場合のみ)
        if surge_prob >= (AI_CONFIDENCE_THRESHOLD - 0.1) and surge_prob > dump_prob: # 少し広めの範囲でシグナル候補を収集
            long_signals.append({'type': 'long', **token_info})
        elif dump_prob >= (AI_CONFIDENCE_THRESHOLD - 0.1) and dump_prob > surge_prob:
            short_signals.append({'type': 'short', **token_info})
            
        # ソートして最も強いシグナルを上位に
        long_signals.sort(key=lambda x: x['surge_probability'], reverse=True)
        short_signals.sort(key=lambda x: x['dump_probability'], reverse=True)
        
        # 通知のクールダウンチェックと送信
        # 通知はNotifierモジュールが責任を持つ
        # ここでは、AIの予測自体が通知閾値を超えている場合に通知
        if (surge_prob >= NOTIFICATION_COOLDOWN_HOURS) or (dump_prob >= NOTIFICATION_COOLDOWN_HOURS):
            # 現状ではanalyze_and_notifyが直接botとやり取りするため、
            # 通知クールダウンはnotifier内部で管理されるべき
            # analyzerは「通知すべき」という情報をnotifierに渡す
            # 例えば、format_and_send_notification内でクールダウンをチェックする
            pass # この例では一旦クールダウンチェックはnotifierに任せる

    # --- トレーダーのロジックを実行 ---
    # 最も強いロング/ショートシグナルと全ての詳細指標をトレーダーに渡す
    logger.info(f"Passing {len(long_signals)} long signals and {len(short_signals)} short signals to trader.")
    execute_trade_logic(long_signals, short_signals, all_indicators, overview={}) # overviewはダミー
    
    logger.info("Analysis cycle completed.")

