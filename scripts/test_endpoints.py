"""J-Quants v2 エンドポイント探索"""
import os
from dotenv import load_dotenv
import requests

load_dotenv()
API_KEY = os.environ["JQUANTS_API_KEY"]
BASE_URL = "https://api.jquants.com/v2"
headers = {"x-api-key": API_KEY}

candidates = [
    "/equities/info",
    "/equities/listed/info",
    "/equities/listings",
    "/equities",
    "/markets/info",
    "/markets/listings",
    "/reference/companies",
    "/listed/companies",
]

for path in candidates:
    resp = requests.get(
        f"{BASE_URL}{path}", headers=headers,
        params={"code": "7203"}, timeout=10,
    )
    print(f"{path}: {resp.status_code} - {resp.text[:150]}")
