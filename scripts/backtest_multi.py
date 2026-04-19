"""複数基準日でバックテストを連続実行し、時系列頑健性を確認"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest import run_backtest  # noqa: E402


DEFAULT_BASE_DATES = [
    "2024-10-21",
    "2025-01-20",
    "2025-04-21",
    "2025-07-21",
    "2025-10-19",
]


def main(scale: str = "core30", holding_days: int = 90, top_n: int = 10, cost: float = 0.2, base_dates: list[str] | None = None) -> None:
    base_dates = base_dates or DEFAULT_BASE_DATES

    results = []
    for bd_str in base_dates:
        bd = date.fromisoformat(bd_str)
        print(f"\n{'=' * 60}")
        print(f"基準日 {bd}")
        print("=" * 60)
        try:
            r = run_backtest(bd, holding_days, top_n, scale, cost_roundtrip_pct=cost)
            results.append(r)
        except Exception as e:
            print(f"ERROR {bd}: {e}")

    # サマリー表 (gross / net)
    print("\n\n" + "=" * 90)
    print(f"時系列サマリー (コスト往復{cost}%差引の net 併記)")
    print("=" * 90)
    print(f"{'基準日':<12} {'Top gross':>10} {'Top net':>10} {'TOPIX':>8} {'超過 gross':>11} {'超過 net':>10} {'勝率 net':>10}")
    for r in results:
        s = r["summary"]
        print(
            f"{r['base_date']:<12} "
            f"{str(s.get('avg_return_top_pct')):>9}% "
            f"{str(s.get('avg_return_top_net_pct')):>9}% "
            f"{str(s.get('topix_return_pct')):>7}% "
            f"{str(s.get('excess_vs_topix_pct')):>10}% "
            f"{str(s.get('excess_vs_topix_net_pct')):>9}% "
            f"{str(s.get('win_rate_top_net_pct')):>9}%"
        )

    # 集計 (gross と net 両方)
    excess_gross = [r["summary"].get("excess_vs_topix_pct") for r in results if r["summary"].get("excess_vs_topix_pct") is not None]
    excess_net = [r["summary"].get("excess_vs_topix_net_pct") for r in results if r["summary"].get("excess_vs_topix_net_pct") is not None]
    avg_excess_gross = sum(excess_gross) / len(excess_gross) if excess_gross else None
    avg_excess_net = sum(excess_net) / len(excess_net) if excess_net else None
    if excess_gross:
        win_g = sum(1 for e in excess_gross if e > 0)
        print(f"\n平均超過リターン gross (vs TOPIX): {avg_excess_gross:+.2f}%  ({win_g}/{len(excess_gross)}期)")
    if excess_net:
        win_n = sum(1 for e in excess_net if e > 0)
        print(f"平均超過リターン net   (vs TOPIX): {avg_excess_net:+.2f}%  ({win_n}/{len(excess_net)}期)")

    out = Path(__file__).resolve().parent.parent / "data" / f"backtest_multi_{scale}_{holding_days}d.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "runs": results,
            "cost_roundtrip_pct": cost,
            "avg_excess_vs_topix": avg_excess_gross,
            "avg_excess_vs_topix_net": avg_excess_net,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n→ {out}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=str, default="core30", choices=["core30", "large70", "all"])
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--cost", type=float, default=0.2, help="往復取引コスト (%) デフォルト0.2")
    parser.add_argument("--base-dates", type=str, default=None, help="カンマ区切り基準日 (例: 2024-10-21,2025-01-20)")
    args = parser.parse_args()
    base_dates = [d.strip() for d in args.base_dates.split(",")] if args.base_dates else None
    main(scale=args.scale, holding_days=args.days, top_n=args.top_n, cost=args.cost, base_dates=base_dates)
