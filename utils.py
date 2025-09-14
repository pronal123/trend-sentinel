# utils.py
import time
import logging
from functools import wraps

def api_retry_decorator(retries=3, delay=5):
    """
    API呼び出しが失敗した場合に、指定回数リトライするデコレータ。
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logging.warning(f"API call to {func.__name__} failed: {e}. Retrying in {delay}s... ({i+1}/{retries})")
                    time.sleep(delay)
            logging.error(f"API call to {func.__name__} failed after {retries} retries.")
            return None # or return pd.DataFrame() for pandas functions
        return wrapper
    return decorator
