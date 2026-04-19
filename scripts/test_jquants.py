"""J-Quants API接続テスト"""
import os
from dotenv import load_dotenv
import requests

load_dotenv()
API_KEY = os.environ["JQUANTS_API_KEY"]
BASE_URL = "https://api.jquants.com/v2"

headers = {"x-api-key": API_KEY}

# 試しにトヨタ(7203)の日足を取る
resp = requests.get(
    f"{BASE_URL}/equities/bars/daily",
    headers=headers,
    params={"code": "7203", "date": "20240104"},
    timeout=10,
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")
