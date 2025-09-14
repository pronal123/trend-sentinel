# main.py
import os
import threading
import time
import logging
from flask import Flask

# 他のファイルから必要なクラスや関数をインポート
from data_aggregator import DataAggregator
from analysis_engine import AnalysisEngine
from telegram_notifier import TelegramNotifier
from state_manager import StateManager
from trading_executor import TradingExecutor
import risk_filter

# --- 初期設定 ---
# ログ設定: BOTの動作記録を詳細に出力
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 各モジュールのインスタンス（実体）を作成
state = StateManager()
data_agg = DataAggregator()
analyzer = AnalysisEngine()
trader = TradingExecutor(state) # state_managerを共有し、ポジション情報を一元管理
notifier = TelegramNotifier()
app = Flask(__name__)

# --- Webサーバー機能 ---
@app.route('/')
def health_check():
    """RenderのヘルスチェックやUptimeRobotからのアクセスに応答する"""
    return "Auto Trading Bot is alive and well!"

# --- BOTのメインロジック ---
def bot_runner_logic():
    """
    BOTのメイン処理。スケジュールに従って分析と取引を無限に繰り返す。
    この関数がバックグラウンドで動き続ける。
    """
    logging.info("🤖 Trading Bot runner has started in the background.")
    
    # 無限ループでBOTを稼働させ続ける
    while True:
        try:
            # 1. データ収集 -> リスク除外
            logging.info("Cycle Start: Fetching market data...")
            all_data = data_agg.get_all_chains_data()
            
            if all_data.empty:
                logging.warning("No data fetched. Skipping this cycle.")
                time.sleep(1800) # データ取得失敗時は30分待機
                continue

            safe_data = risk_filter.filter_risky_tokens(all_data)

            # 2. 分析
            logging.info("Analyzing data for trading signals...")
            long_df, short_df, spike_df, summary = analyzer.run_analysis(safe_data)

            # 3. 通知 (重複防止機能付き)
            long_to_notify = long_df[long_df['symbol'].apply(state.can_notify)]
            short_to_notify = short_df[short_df['symbol'].apply(state.can_notify)]
            spike_to_notify = spike_df[spike_df['symbol'].apply(state.can_notify)]

            if not (long_to_notify.empty and short_to_notify.empty and spike_to_notify.empty):
                logging.info("Significant signals found. Sending Telegram notification.")
                notifier.send_notification(long_to_notify, short_to_notify, spike_to_notify, summary)
                # 通知した銘柄を記録
                state.record_notification(long_to_notify)
                state.record_notification(short_to_notify)
                state.record_notification(spike_to_notify)

            # 4. 取引実行
            logging.info("Executing trades based on analysis...")
            # LONG候補のトップ1銘柄を取引 (一度に多くのポジションを持たない戦略)
            if not long_to_notify.empty:
                top_long_candidate = long_to_notify.iloc[0]
                logging.info(f"Top LONG candidate: {top_long_candidate['symbol'].upper()}")
                trader.execute_long(top_long_candidate['id'])
            
            # SHORT候補に合致する保有中の銘柄があれば売却
            for _, short_candidate in short_df.iterrows():
                if state.has_position(short_candidate['id']):
                    logging.info(f"SHORT signal for owned asset: {short_candidate['symbol'].upper()}")
                    trader.execute_short(short_candidate['id'])

            # 5. 次の実行まで待機 (例: 1時間)
            logging.info(f"--- Cycle Finished. Waiting for 1 hour. ---")
            time.sleep(3600)

        except Exception as e:
            # 予期せぬエラーが発生してもBOTが停止しないように、エラー内容を記録して処理を継続
            logging.error(f"❌ An critical error occurred in the main bot loop: {e}", exc_info=True)
            # エラー発生時は5分待機して継続
            time.sleep(300)

# --- プログラムの起動部分 ---
if __name__ == "__main__":
    # BOTのメインロジックをバックグラウンドのスレッドで実行
    bot_thread = threading.Thread(target=bot_runner_logic)
    bot_thread.daemon = True
    bot_thread.start()

    # RenderでWeb Serviceとして稼働させるためにFlaskサーバーを起動
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"🌐 Starting web server on port {port}...")
    
    # このスクリプトを直接実行した場合(ローカルテストなど)はFlaskの開発サーバーが起動
    # Render上ではGunicornがこのファイルを呼び出して本番サーバーを起動する
    app.run(host='0.0.0.0', port=port)

