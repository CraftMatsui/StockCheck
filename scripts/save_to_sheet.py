"""プライマリ推薦とセカンドオピニオンを Googleシートに保存

入力:
  data/primary_recommendations.json
  data/second_opinion.json

出力:
  Googleシートの recommendations ワークシート
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import sheets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

REC_SHEET = "recommendations"
REC_HEADERS = [
    "generated_at", "code", "name", "sector", "current_price",
    "technical_score", "technical_reason",
    "fundamental_score", "fundamental_reason",
    "target_price", "stop_loss", "fair_value", "valuation_risk",
    "second_opinion_level", "contrarian_view", "blind_spots", "verdict",
]


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    primary = _read(DATA / "primary_recommendations.json")
    opinion = _read(DATA / "second_opinion.json")

    rev_by_code = {r["code"]: r for r in opinion.get("reviews", [])}
    today = date.today().isoformat()

    book = sheets._open_book()
    ws = sheets._ensure_worksheet(book, REC_SHEET, REC_HEADERS)
    # 毎朝上書き運用なので既存データをクリア (ヘッダだけ残す)
    ws.clear()
    ws.append_row(REC_HEADERS)

    rows = []
    for p in primary["recommendations"]:
        op = rev_by_code.get(p["code"], {})
        blind_spots = op.get("blind_spots", [])
        if isinstance(blind_spots, list):
            blind_spots = " / ".join(blind_spots)
        rows.append([
            today,
            p["code"],
            p["name"],
            p.get("sector17", ""),
            p.get("current_price", ""),
            p.get("technical_score", ""),
            p.get("technical_reason", "") or "",
            p.get("fundamental_score", ""),
            p.get("fundamental_reason", "") or "",
            p.get("target_price", "") or "",
            p.get("stop_loss", "") or "",
            p.get("fair_value", "") or "",
            p.get("valuation_risk", "") or "",
            op.get("concern_level", ""),
            op.get("contrarian_view", ""),
            blind_spots,
            op.get("verdict", ""),
        ])
    if rows:
        ws.append_rows(rows)
    print(f"✓ {REC_SHEET} シートに {len(rows)} 銘柄保存しました")


if __name__ == "__main__":
    main()
