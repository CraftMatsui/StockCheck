"""TOPIX500から候補50銘柄を絞り込むスクリーニングスクリプト

出力: data/candidates.json
  - 各銘柄に価格指標(52週高値接近度、出来高比、モメンタム、ATR)と
    ファンダ指標(PER, PBR, ROE, 配当利回り, 売上成長率)を付与
"""
import json
import sys
import math
from datetime import date, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import jquants  # noqa: E402
from lib.technical import compute_price_metrics  # noqa: E402
from lib.scoring import is_topix500 as _is_topix500, compute_fundamentals, score_stock, passes_liquidity_filter, LIQUIDITY_THRESHOLD_YEN  # noqa: E402,F401

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "candidates.json"
LOOKBACK_DAYS = 365  # 約1年


def main(top_n: int = 50, limit: int | None = None) -> None:
    today = date.today()
    start = today - timedelta(days=LOOKBACK_DAYS + 30)  # 営業日換算の余裕

    print(f"[1/4] 全銘柄マスタ取得...")
    all_eq = jquants.list_all_equities()
    print(f"  全銘柄: {len(all_eq)}件")

    # ScaleCat のユニーク値を表示（初回デバッグ用）
    scales = {}
    for e in all_eq:
        sc = e.get("ScaleCat", "")
        scales[sc] = scales.get(sc, 0) + 1
    print(f"  ScaleCat 分布: {scales}")

    topix500 = [e for e in all_eq if _is_topix500(e.get("ScaleCat", ""))]
    print(f"  TOPIX500相当: {len(topix500)}件")
    if limit:
        topix500 = topix500[:limit]
        print(f"  → limit={limit} により {len(topix500)}件だけ処理")

    if not topix500:
        print("ERROR: TOPIX500銘柄が0件です。ScaleCatの値を確認してください。")
        sys.exit(1)

    # 銘柄コードは末尾0つきの5桁 (例: "72030") → 先頭4桁に変換
    def code4(c: str) -> str:
        return c[:-1] if len(c) == 5 else c

    print(f"\n[2/4] 日足・財務データ取得 ({len(topix500)}銘柄 x 2コール)...")
    enriched = []
    for i, eq in enumerate(topix500, 1):
        code5 = eq["Code"]
        code = code4(code5)
        name = eq.get("CoName", "")

        if i % 25 == 0 or i == len(topix500):
            print(f"  {i}/{len(topix500)} {code} {name}")

        try:
            bars = jquants.get_daily_bars(code, start, today)
            jquants.throttled_sleep(0.2)
            summary = jquants.get_financial_summary(code)
            jquants.throttled_sleep(0.2)
        except Exception as e:
            print(f"  skip {code} {name}: {e}")
            continue

        price_m = compute_price_metrics(bars)
        if not price_m:
            continue
        fund_m = compute_fundamentals(summary, price_m.get("current"))

        enriched.append({
            "code": code,
            "name": name,
            "sector17": eq.get("S17Nm", ""),
            "sector33": eq.get("S33Nm", ""),
            "scale": eq.get("ScaleCat", ""),
            "price": price_m,
            "fundamental": fund_m,
            "score": score_stock(price_m, fund_m),
        })

    print(f"\n[3/4] スコアリング & 絞り込み...")
    # 流動性フィルタ: 日次売買代金20日平均 < 3億円 の銘柄は除外
    before = len(enriched)
    enriched = [e for e in enriched if passes_liquidity_filter(e.get("price", {}))]
    print(f"  流動性フィルタ (>={int(LIQUIDITY_THRESHOLD_YEN/1e8)}億円/日): {before} → {len(enriched)}銘柄")
    enriched.sort(key=lambda x: x["score"], reverse=True)
    candidates = enriched[:top_n]

    print(f"\n[4/4] 結果を書き出し...")
    OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    with OUTPUT.open("w", encoding="utf-8") as f:
        json.dump({
            "generated_at": today.isoformat(),
            "total_screened": len(enriched),
            "candidates": candidates,
        }, f, ensure_ascii=False, indent=2)
    print(f"  → {OUTPUT} ({len(candidates)}銘柄)")

    # トップ10をプレビュー
    print("\n=== トップ10 プレビュー ===")
    for c in candidates[:10]:
        p, f = c["price"], c["fundamental"]
        print(
            f"  {c['code']} {c['name'][:12]:12s}  "
            f"score={c['score']:5.1f}  "
            f"price={p.get('current')}  "
            f"PER={f.get('per')}  PBR={f.get('pbr')}  ROE={f.get('roe')}%  "
            f"52wH={p.get('pct_from_high')}%"
        )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="処理する銘柄数の上限 (動作確認用)")
    parser.add_argument("--top-n", type=int, default=50, help="最終的に残す候補数")
    args = parser.parse_args()
    main(top_n=args.top_n, limit=args.limit)
