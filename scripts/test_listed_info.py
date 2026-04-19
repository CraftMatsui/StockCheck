"""J-Quants 銘柄情報エンドポイント確認"""
import os
from dotenv import load_dotenv
import requests

load_dotenv()
API_KEY = os.environ["JQUANTS_API_KEY"]
BASE_URL = "https://api.jquants.com/v2"
headers = {"x-api-key": API_KEY}

# listed/infoを試す
resp = requests.get(
    f"{BASE_URL}/listed/info",
    headers=headers,
    params={"code": "7203"},
    timeout=10,
)
print(f"listed/info Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")
