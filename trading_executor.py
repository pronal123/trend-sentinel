import os
import time
import hmac
import hashlib
import requests
import logging
from state_manager import StateManager

class TradingExecutor:
    def __init__(self, api_key, api_secret, passphrase, symbol="BTCUSDT_UMCBL"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.symbol = symbol
        self.base_url = "https://api.bitget.com"
        self.state_manager = StateManager()

        # Telegram設定
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def _sign(self, method, path, body=""):
        timestamp = str(int(time.time() * 1000))
        prehash = timestamp + method + path + body
        sign = hmac.new(
            self.api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return timestamp, sign

    def _headers(self, method, path, body=""):
        timestamp, sign = self._sign(method, path, body)
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

    def open_position(self, side, size, entry_price, tp, sl):
        try:
            url = f"{self.base_url}/api/mix/v1/order/placeOrder"
            body = {
                "symbol": self.symbol,
                "marginCoin": "USDT",
                "size": str(size),
                "side": "open_long" if side == "long" else "open_short",
                "orderType": "market",
                "timeInForceValue": "normal",
                "reduceOnly": False
            }
            res = requests.post(url, headers=self._headers("POST", "/api/mix/v1/order/placeOrder", ""), json=body)
            res_json = res.json()

            if res.status_code == 200 and res_json.get("msg") == "success":
                logging.info(f"新規建玉成功 {side} {size} {self.symbol}")
                self.state_manager.add_position(self.symbol, side, entry_price, size, tp, sl)
                self._notify_telegram(f"✅ 新規建玉: {self.symbol} {side}\n数量: {size}\n価格: {entry_price}\nTP: {tp}, SL: {sl}")
            else:
                logging.error(f"建玉失敗 {res_json}")
        except Exception as e:
            logging.error(f"open_position エラー: {e}")

    def close_position(self, position, exit_price, reason="manual"):
        try:
            url = f"{self.base_url}/api/mix/v1/order/placeOrder"
            body = {
                "symbol": position["symbol"],
                "marginCoin": "USDT",
                "size": str(position["size"]),
                "side": "close_long" if position["side"] == "long" else "close_short",
                "orderType": "market",
                "timeInForceValue": "normal",
                "reduceOnly": True
            }
            res = requests.post(url, headers=self._headers("POST", "/api/mix/v1/order/placeOrder", ""), json=body)
            res_json = res.json()

            if res.status_code == 200 and res_json.get("msg") == "success":
                logging.info(f"ポジション決済成功 {position['side']} {position['symbol']} @ {exit_price}")
                self.state_manager.close_position(position["symbol"], exit_price, reason)
                pnl = (exit_price - position["entry_price"]) * position["size"] if position["side"] == "long" else (position["entry_price"] - exit_price) * position["size"]
                self._notify_telegram(
                    f"💰 決済完了: {position['symbol']} {position['side']}\n"
                    f"数量: {position['size']}\nExit価格: {exit_price}\n"
                    f"理由: {reason.upper()}\n損益: {pnl:.2f} USDT"
                )
            else:
                logging.error(f"決済失敗 {res_json}")
        except Exception as e:
            logging.error(f"close_position エラー: {e}")

    def _notify_telegram(self, message: str):
        if not self.tg_token or not self.tg_chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            payload = {"chat_id": self.tg_chat_id, "text": message}
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"Telegram通知失敗: {e}")
