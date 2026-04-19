"""テクニカル+ファンダメンタル推薦を統合して最終10銘柄を決める

入力:
  data/technical_recommendations.json
  data/fundamental_recommendations.json
  data/candidates.json (現在値・業種情報の参照用)

出力:
  data/primary_recommendations.json
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

from lib.scoring import select_with_sector_cap, SECTOR_CAP_DEFAULT  # noqa: E402


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    tech = _read(DATA / "technical_recommendations.json")
    fund = _read(DATA / "fundamental_recommendations.json")
    cand = _read(DATA / "candidates.json")

    cand_by_code = {c["code"]: c for c in cand["candidates"]}
    tech_by_code = {r["code"]: r for r in tech["recommendations"]}
    fund_by_code = {r["code"]: r for r in fund["recommendations"]}

    all_codes = set(tech_by_code) | set(fund_by_code)

    merged = []
    for code in all_codes:
        t = tech_by_code.get(code)
        f = fund_by_code.get(code)
        c = cand_by_code.get(code)
        if not c:
            continue

        t_score = t["technical_score"] if t else 0
        f_score = f["fundamental_score"] if f else 0
        combined = t_score + f_score
        # 両者カバーなら1.5倍の優先度
        if t and f:
            combined *= 1.5

        merged.append({
            "code": code,
            "name": c["name"],
            "sector17": c.get("sector17"),
            "scale": c.get("scale"),
            "current_price": c["price"].get("current"),
            "technical_score": t_score,
            "fundamental_score": f_score,
            "combined_score": round(combined, 2),
            "technical_reason": t["technical_reason"] if t else None,
            "fundamental_reason": f["fundamental_reason"] if f else None,
            "target_price": t["target_price"] if t else None,
            "stop_loss": t["stop_loss"] if t else None,
            "fair_value": f["fair_value"] if f else None,
            "valuation_risk": f["valuation_risk"] if f else None,
            "both_agree": bool(t and f),
        })

    # セクター集中ペナルティ: sector17 ごと最大 SECTOR_CAP_DEFAULT 銘柄まで
    primary = select_with_sector_cap(
        merged, top_n=10, cap=SECTOR_CAP_DEFAULT, sector_key="sector17", score_key="combined_score"
    )
    print(f"  セクターcap={SECTOR_CAP_DEFAULT}適用: {len(merged)} → {len(primary)}銘柄")

    out = {
        "generated_at": date.today().isoformat(),
        "recommendations": primary,
    }
    path = DATA / "primary_recommendations.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✓ {path} に {len(primary)} 銘柄書き出し")
    for p in primary:
        mark = "●" if p["both_agree"] else "○"
        print(
            f"  {mark} {p['code']} {p['name'][:14]:14s}  "
            f"T={p['technical_score']}  F={p['fundamental_score']}  "
            f"目安={p['target_price']}/{p['stop_loss']}"
        )


if __name__ == "__main__":
    main()
