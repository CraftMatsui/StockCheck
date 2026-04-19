"""J-Quants API クライアント"""
from datetime import date, timedelta
from typing import Optional
import time
import requests
from .config import JQUANTS_API_KEY

BASE_URL = "https://api.jquants.com/v2"
HEADERS = {"x-api-key": JQUANTS_API_KEY}


def _get(path: str, params: dict, timeout: int = 30, max_retry: int = 5) -> dict:
    """429(レート制限)のときは指数バックオフで再試行"""
    for attempt in range(max_retry):
        r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=timeout)
        if r.status_code == 429:
            wait = min(60, 5 * (2 ** attempt))  # 5, 10, 20, 40, 60秒
            print(f"    [429] rate limited, waiting {wait}s... (attempt {attempt+1}/{max_retry})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"max retries exceeded for {path} {params}")


def get_company_info(code: str) -> Optional[dict]:
    """銘柄マスタから会社名・業種を取得"""
    data = _get("/equities/master", {"code": code}).get("data", [])
    return data[0] if data else None


def list_all_equities() -> list[dict]:
    """全上場銘柄マスタ (約4,500件)"""
    return _get("/equities/master", {}).get("data", [])


def get_latest_close(code: str, lookback_days: int = 10) -> Optional[dict]:
    """直近営業日の終値"""
    today = date.today()
    start = today - timedelta(days=lookback_days)
    data = _get(
        "/equities/bars/daily",
        {"code": code, "from": start.strftime("%Y%m%d"), "to": today.strftime("%Y%m%d")},
    ).get("data", [])
    return data[-1] if data else None


def get_daily_bars(code: str, from_date: date, to_date: date) -> list[dict]:
    """期間指定で日足を取得"""
    return _get(
        "/equities/bars/daily",
        {"code": code, "from": from_date.strftime("%Y%m%d"), "to": to_date.strftime("%Y%m%d")},
    ).get("data", [])


def get_financial_summary(code: str) -> list[dict]:
    """財務サマリー履歴 (古い順)"""
    return _get("/fins/summary", {"code": code}).get("data", [])


def throttled_sleep(seconds: float = 0.1) -> None:
    """APIレート制限対策の軽いスリープ"""
    time.sleep(seconds)
