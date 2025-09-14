import os
import hmac
import hashlib
import time
import requests
import logging

class TradingExecutor:
    BASE_URL = "https://api.bitget.com"

    def __init__(self):
        self.api_key = os.getenv("BITGET_API_KEY")
        self.secret = os.getenv("BITGET_API_SECRET")
        self.passphrase = os.getenv("BITGET_API_PASSPHRASE")
        self.account_type = os.getenv("BITGET_ACCOUNT_TYPE", "spot")  # spot or futures

        if not all([self.api_key, self.secret, self.passphrase]):
            raise ValueError("Bitget API認証情報が不足しています (.env を確認してください)")

    def _sign(self, method: str, endpoint: str, params: str = ""):
        ts = str(int(time.time() * 1000))
        prehash = ts + method + endpoint + params
        sign = hmac.new(self.secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).hexdigest()
        return ts, sign

    def _headers(self, method: str, endpoint: str, params: str = ""):
        ts, sign = self._sign(method, endpoint, params)
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

    def place_order(self, symbol: str, side: str, size: float, price: float = None, leverage: int = 1):
        """
        side: buy/sell
        size: 注文数量
        price: Noneなら成行
        leverage: 先物の場合のレバレッジ
        """
        if self.account_type == "spot":
            endpoint = "/api/spot/v1/trade/orders"
            url = self.BASE_URL + endpoint
            data = {
                "symbol": symbol,
                "side": side,
                "orderType": "limit" if price else "market",
                "force": "gtc",
                "price": str(price) if price else "",
                "quantity": str(size)
            }
        else:  # futures
            endpoint = "/api/mix/v1/order/placeOrder"
            url = self.BASE_URL + endpoint
            data = {
                "symbol": symbol,
                "marginCoin": "USDT",
                "side": "open_long" if side == "buy" else "open_short",
                "orderType": "limit" if price else "market",
                "price": str(price) if price else "",
                "size": str(size),
                "leverage": str(leverage),
                "timeInForceValue": "normal"
            }

        headers = self._headers("POST", endpoint, "")
        try:
            r = requests.post(url, headers=headers, json=data, timeout=10)
            res = r.json()
            logging.info(f"Order response: {res}")
            return res
        except Exception as e:
            logging.error(f"注文エラー: {e}")
            return None

    def close_position(self, symbol: str, side: str, size: float):
        """ 先物ポジションのクローズ """
        if self.account_type != "futures":
            logging.warning("close_position は futures アカウントのみ対応")
            return None

        endpoint = "/api/mix/v1/order/placeOrder"
        url = self.BASE_URL + endpoint
        data = {
            "symbol": symbol,
            "marginCoin": "USDT",
            "side": "close_long" if side == "buy" else "close_short",
            "orderType": "market",
            "size": str(size),
            "timeInForceValue": "normal"
        }
        headers = self._headers("POST", endpoint, "")
        try:
            r = requests.post(url, headers=headers, json=data, timeout=10)
            res = r.json()
            logging.info(f"Close response: {res}")
            return res
        except Exception as e:
            logging.error(f"クローズ注文エラー: {e}")
            return None
