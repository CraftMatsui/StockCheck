"""J-Quants Standard で取れるデータを確認するための探索スクリプト"""
import os
import json
from dotenv import load_dotenv
import requests

load_dotenv()
API_KEY = os.environ["JQUANTS_API_KEY"]
BASE_URL = "https://api.jquants.com/v2"
headers = {"x-api-key": API_KEY}


def probe(path: str, params: dict, label: str) -> dict | None:
    print(f"\n===== {label} ({path}) =====")
    print(f"params: {params}")
    r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=30)
    print(f"status: {r.status_code}")
    if r.status_code != 200:
        print(f"body: {r.text[:200]}")
        return None
    data = r.json()
    for k, v in data.items():
        if isinstance(v, list) and v:
            print(f"{k}[0]:")
            print(json.dumps(v[0], indent=2, ensure_ascii=False)[:1200])
            print(f"(total {len(v)} records)")
        else:
            print(f"{k}: {str(v)[:200]}")
    return data


# 財務系（/fins/）
probe("/fins/summary", {"code": "7203"}, "財務サマリー トヨタ")
probe("/fins/details", {"code": "7203"}, "財務諸表 トヨタ")
probe("/fins/dividend", {"code": "7203"}, "配当 トヨタ")

# その他
probe("/equities/earnings-calendar", {"code": "7203"}, "決算発表日 トヨタ")
probe("/indices/bars/daily/topix", {"from": "20260401", "to": "20260417"}, "TOPIX日足")
