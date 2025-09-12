import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
import joblib # モデルの保存・ロード用
import logging
import os
from datetime import datetime

from config import MODEL_PATH, MODEL_DIR, ML_LABEL_LOOKBACK_HOURS, ML_PRICE_GROWTH_THRESHOLD

logger = logging.getLogger(__name__)

# グローバル変数としてモデルとスケーラーを初期化
scaler = None
model = None

def create_features(df):
    """OHLCVデータから特徴量を作成する"""
    df = df.dropna()
    if df.empty or len(df) < 50: # RSI/MAの計算に十分なデータがない場合を考慮
        logger.warning("Not enough data to create features.")
        return pd.DataFrame()

    # 価格の変動率
    df['price_change'] = df['close'].pct_change()
    # ボリュームの変動率
    df['volume_change'] = df['volume'].pct_change()
    # 高値と安値の差
    df['high_low_diff'] = (df['high'] - df['low']) / df['close']
    # 終値と始値の差
    df['close_open_diff'] = (df['close'] - df['open']) / df['open']
    
    # 複数期間の移動平均
    df['ma_7'] = df['close'].rolling(window=7).mean()
    df['ma_25'] = df['close'].rolling(window=25).mean()
    
    # RSI (簡易版)
    delta = df['close'].diff()
    # gainとlossの計算でNaNが発生しないように
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    
    # zero division回避
    rs = gain / (loss.replace(0, np.nan)) # lossが0の場合を考慮
    df['rsi_14'] = 100 - (100 / (1 + rs))

    df = df.dropna() # NaN値を含む行を削除
    
    if df.empty:
        logger.warning("DataFrame became empty after feature creation and dropping NaN.")
        return pd.DataFrame()

    # 使用する特徴量を選択
    features = df[['price_change', 'volume_change', 'high_low_diff', 'close_open_diff', 'ma_7', 'ma_25', 'rsi_14']]
    return features

def create_labels(df, lookback_hours=ML_LABEL_LOOKBACK_HOURS, price_growth_threshold=ML_PRICE_GROWTH_THRESHOLD):
    """OHLCVデータからラベルを作成する (価格上昇/下落)"""
    if len(df) < lookback_hours + 1:
        logger.warning(f"Not enough data ({len(df)} rows) to create labels for lookback {lookback_hours} hours.")
        return pd.Series(dtype=int)

    # 将来の価格変化を計算 (lookback_hours後の価格)
    future_close_prices = df['close'].shift(-lookback_hours)
    price_change = (future_close_prices - df['close']) / df['close']

    # ラベル付け: 0=down (変化なし含む), 1=up
    labels = (price_change > price_growth_threshold).astype(int)

    # 未来のデータポイントはラベルがないので削除
    return labels.iloc[:-lookback_hours]

def preprocess_data(ohlcv_df, is_training=False):
    """生OHLCVデータを機械学習モデル用の特徴量に変換する"""
    if ohlcv_df.empty:
        logger.warning("Empty DataFrame provided for preprocessing.")
        return pd.DataFrame()

    features_df = create_features(ohlcv_df)
    if features_df.empty:
        logger.warning("No features generated after creation.")
        return pd.DataFrame()

    global scaler
    if is_training:
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features_df)
    else:
        if scaler is None:
            # モデルロード時にスケーラーもロードされるはずだが、念のため
            load_model() # モデルと一緒にスケーラーをロードを試みる
            if scaler is None:
                logger.warning("Scaler not loaded/trained. Initializing a new StandardScaler (may affect prediction accuracy).")
                scaler = StandardScaler()
                scaler.fit(features_df) # 現在のデータでfit (理想は学習データでfitしたもの)

        try:
            scaled_features = scaler.transform(features_df)
        except Exception as e:
            logger.error(f"Error during feature scaling with loaded scaler: {e}. Attempting to re-fit scaler.", exc_info=True)
            scaler = StandardScaler()
            scaler.fit(features_df)
            scaled_features = scaler.transform(features_df)


    return pd.DataFrame(scaled_features, columns=features_df.columns, index=features_df.index)

def train_model(db_path=None, model_path=MODEL_PATH):
    """
    データ取得、特徴量・ラベル作成、モデル学習、保存を行う。
    db_pathは学習データを取得するためのデータベース接続情報。
    """
    logger.info("Starting ML model training...")

    # TODO: ここで実際のデータベースから過去のOHLCVデータを取得するロジックを実装する
    # 例: database.get_historical_ohlcv_for_training()
    # 現状ではダミーデータを使用するため、実運用では置き換えること
    
    # ダミーデータの生成 (実際のデータに置き換えること)
    num_samples = 1000
    # 終値がランダムウォークするように調整
    close_prices = 1000 + np.cumsum(np.random.normal(0, 5, num_samples)) 
    df_data = {
        'open': close_prices - np.random.rand(num_samples) * 10,
        'high': close_prices + np.random.rand(num_samples) * 10,
        'low': close_prices - np.random.rand(num_samples) * 10,
        'close': close_prices,
        'volume': np.random.rand(num_samples) * 1000000 + 100000
    }
    dummy_ohlcv_df = pd.DataFrame(df_data, index=pd.to_datetime(pd.date_range(end=datetime.now(), periods=num_samples, freq='H')))
    dummy_ohlcv_df.index.name = 'timestamp' # インデックス名を設定

    # 特徴量とラベルを作成
    features = preprocess_data(dummy_ohlcv_df, is_training=True) # 学習時はスケーラーをfit
    labels = create_labels(dummy_ohlcv_df)

    # 特徴量とラベルのインデックスを合わせて、NaN行を除去
    combined_df = pd.concat([features, labels.rename('label')], axis=1).dropna()
    if combined_df.empty:
        logger.error("Combined DataFrame is empty after feature/label creation and dropping NaN. Not enough data to train.")
        return

    features = combined_df[features.columns]
    labels = combined_df['label']

    if features.empty or labels.empty:
        logger.error("Not enough data to train the model after feature/label creation.")
        return
    
    logger.info(f"Training data shape: Features {features.shape}, Labels {labels.shape}")

    # モデルの学習 (RandomForestClassifierの例)
    global model
    model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    model.fit(features, labels)
    
    # 学習済みモデルとスケーラーをファイルに保存
    os.makedirs(MODEL_DIR, exist_ok=True) # ディレクトリが存在しない場合に作成
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, MODEL_PATH.replace('.joblib', '_scaler.joblib')) # スケーラーも保存
    
    logger.info(f"Model and scaler trained and saved to {MODEL_PATH} and {MODEL_PATH.replace('.joblib', '_scaler.joblib')}")

def load_model(model_path=MODEL_PATH):
    """
    保存されたモデルとスケーラーをロードする。
    ロードに失敗した場合はNoneを返す。
    """
    global model, scaler
    
    # 既にロード済みなら再ロードしない
    if model is not None and scaler is not None:
        logger.debug("ML model and scaler already loaded.")
        return model

    try:
        if os.path.exists(model_path):
            model = joblib.load(model_path)
            logger.info(f"ML model loaded from {model_path}")
            
            scaler_path = MODEL_PATH.replace('.joblib', '_scaler.joblib')
            if os.path.exists(scaler_path):
                scaler = joblib.load(scaler_path)
                logger.info(f"Scaler loaded from {scaler_path}")
            else:
                logger.warning(f"Scaler not found at {scaler_path}. This may cause issues if not trained.")
                # スケーラーがない場合、予測時にエラーになる可能性があるので、ここで初期化
                scaler = StandardScaler() 
            
            return model
        else:
            logger.warning(f"ML model file not found at {model_path}. Model needs to be trained.")
            return None
    except Exception as e:
        logger.error(f"Error loading ML model or scaler: {e}", exc_info=True)
        return None

def make_prediction(model_instance, preprocessed_data):
    """
    前処理されたデータを使ってAI予測を行う。
    戻り値: 予測クラス (0:down, 1:up), 確率 ([prob_down, prob_up])
    """
    if model_instance is None:
        logger.error("ML model is not loaded. Cannot make prediction.")
        return None, None
    if preprocessed_data.empty:
        logger.warning("Empty preprocessed data provided for prediction.")
        return None, None
    
    try:
        prediction = model_instance.predict(preprocessed_data)
        probabilities = model_instance.predict_proba(preprocessed_data)
        return prediction[0], probabilities
    except Exception as e:
        logger.error(f"Error making prediction: {e}", exc_info=True)
        return None, None

# サービス起動時に一度モデルをロードしようと試みる
# ここでロードされるのはグローバルなmodelとscaler
load_model()
