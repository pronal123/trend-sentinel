import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
import joblib # モデルの保存・ロード用
import logging
import os

from config import MODEL_PATH, ML_LABEL_LOOKBACK_HOURS, ML_PRICE_GROWTH_THRESHOLD

logger = logging.getLogger(__name__)

# ✅ 修正: 以下の行を削除またはコメントアウト
# from database import save_model_to_db, load_model_from_db

scaler = StandardScaler()
model = None # グローバル変数としてモデルを初期化

def create_features(df):
    """OHLCVデータから特徴量を作成する"""
    # 欠損値があれば除去または補完
    df = df.dropna()
    if df.empty:
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
    
    # RSI (簡易版, ta-libがあればより正確に)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # 不要なNaN行を削除
    df = df.dropna()
    
    if df.empty:
        return pd.DataFrame()

    # 使用する特徴量を選択
    features = df[['price_change', 'volume_change', 'high_low_diff', 'close_open_diff', 'ma_7', 'ma_25', 'rsi_14']]
    return features.iloc[-1:].fillna(0) # 最新のデータポイントのみを返す (予測用)

def create_labels(df, lookback_hours=ML_LABEL_LOOKBACK_HOURS, price_growth_threshold=ML_PRICE_GROWTH_THRESHOLD):
    """OHLCVデータからラベルを作成する (価格上昇/下落/横ばい)"""
    # lookback_hours後の価格変化に基づいてラベルを生成
    # 例: 1時間後の価格がprice_growth_threshold以上上がったら 'up' (1)
    # price_growth_threshold以上下がったら 'down' (0)
    # それ以外は 'neutral' (2) - このモデルでは0, 1の二値分類を想定
    
    if len(df) < lookback_hours + 1:
        return pd.Series(dtype=int)

    # 将来の価格変化を計算 (lookback_hours後の価格)
    future_price = df['close'].shift(-lookback_hours)
    price_change = (future_price - df['close']) / df['close']

    # ラベル付け
    labels = np.zeros(len(df)) # デフォルトは'down' (0)
    labels[price_change > price_growth_threshold] = 1 # 'up' (1)

    return pd.Series(labels, index=df.index).iloc[:-lookback_hours] # 未来データ部分は削除

def preprocess_data(ohlcv_df):
    """生OHLCVデータを機械学習モデル用の特徴量に変換する"""
    if ohlcv_df.empty:
        logger.warning("Empty DataFrame provided for preprocessing.")
        return pd.DataFrame()

    features_df = create_features(ohlcv_df)
    if features_df.empty:
        logger.warning("No features generated after creation and dropping NaN.")
        return pd.DataFrame()

    # スケーリング (モデル学習時に使用したスケーラーを適用)
    # ここでは仮に新しいスケーラーを使用しているが、実際には学習済みのスケーラーをロードすべき
    try:
        if scaler.n_features_in_ is None: # スケーラーがまだfitされていない場合
             # ダミーでfitするか、学習済みスケーラーをロードする
             # 本番では学習済みスケーラーをロードすることを推奨
             scaler.fit(features_df) 
        scaled_features = scaler.transform(features_df)
        return pd.DataFrame(scaled_features, columns=features_df.columns, index=features_df.index)
    except Exception as e:
        logger.error(f"Error during feature scaling: {e}", exc_info=True)
        return pd.DataFrame()

def train_model(db_path=None, model_path=MODEL_PATH):
    """
    データ取得、特徴量・ラベル作成、モデル学習、保存を行う。
    db_pathは学習データを取得するためのデータベース接続情報。
    """
    logger.info("Starting ML model training...")

    # TODO: 実際にはデータベースから過去のOHLCVデータを取得するロジックをここに実装する
    # 例: database.get_historical_ohlcv_for_training()
    # 現状ではダミーデータを使用するか、ファイルからロードするなどが必要
    
    # ダミーデータの生成 (実際のデータに置き換えること)
    num_samples = 1000
    df_data = {
        'open': np.random.rand(num_samples) * 100 + 1000,
        'high': np.random.rand(num_samples) * 10 + df['open'] + 5,
        'low': np.random.rand(num_samples) * 10 - 5 + df['open'],
        'close': np.random.rand(num_samples) * 10 + df['open'],
        'volume': np.random.rand(num_samples) * 1000000
    }
    dummy_ohlcv_df = pd.DataFrame(df_data, index=pd.to_datetime(pd.date_range(end=datetime.now(), periods=num_samples, freq='H')))

    # 特徴量とラベルを作成
    features = create_features(dummy_ohlcv_df)
    labels = create_labels(dummy_ohlcv_df)

    if features.empty or labels.empty or len(features) != len(labels):
        logger.error("Not enough data to train the model after feature/label creation.")
        return

    # データのスケーリング
    global scaler
    scaler = StandardScaler() # 新しいスケーラーをfit
    scaled_features = scaler.fit_transform(features)

    # モデルの学習 (RandomForestClassifierの例)
    global model
    model = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
    model.fit(scaled_features, labels)
    
    # 学習済みモデルとスケーラーをファイルに保存
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(model, model_path)
    joblib.dump(scaler, MODEL_PATH.replace('.joblib', '_scaler.joblib')) # スケーラーも保存
    
    logger.info(f"Model and scaler trained and saved to {model_path} and {MODEL_PATH.replace('.joblib', '_scaler.joblib')}")

def load_model(model_path=MODEL_PATH):
    """
    保存されたモデルとスケーラーをロードする。
    ロードに失敗した場合はNoneを返す。
    """
    global model, scaler
    if model is not None and scaler is not None:
        return model # 既にロード済みなら再ロードしない

    try:
        if os.path.exists(model_path):
            model = joblib.load(model_path)
            logger.info(f"ML model loaded from {model_path}")
            
            scaler_path = MODEL_PATH.replace('.joblib', '_scaler.joblib')
            if os.path.exists(scaler_path):
                scaler = joblib.load(scaler_path)
                logger.info(f"Scaler loaded from {scaler_path}")
            else:
                logger.warning(f"Scaler not found at {scaler_path}. Initializing new StandardScaler (may affect prediction accuracy).")
                scaler = StandardScaler() # スケーラーがない場合は初期化
            
            return model
        else:
            logger.warning(f"ML model file not found at {model_path}. Model needs to be trained.")
            return None
    except Exception as e:
        logger.error(f"Error loading ML model or scaler: {e}", exc_info=True)
        return None

def make_prediction(model, preprocessed_data):
    """
    前処理されたデータを使ってAI予測を行う。
    戻り値: 予測クラス (0:down, 1:up), 確率 ([prob_down, prob_up])
    """
    if model is None:
        logger.error("ML model is not loaded. Cannot make prediction.")
        return None, None
    if preprocessed_data.empty:
        logger.warning("Empty preprocessed data provided for prediction.")
        return None, None
    
    try:
        prediction = model.predict(preprocessed_data)
        probabilities = model.predict_proba(preprocessed_data)
        return prediction[0], probabilities
    except Exception as e:
        logger.error(f"Error making prediction: {e}", exc_info=True)
        return None, None

# サービス起動時に一度モデルをロードしようと試みる
load_model()
