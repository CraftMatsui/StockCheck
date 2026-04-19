"""既存バックテスト JSON に取引コストを適用して net リターンを算出

前提:
- 往復コスト 0.2% (買い 0.1% + 売り 0.1%) — SBI/楽天など国内ネット証券の現物取引想定
  (手数料 + スプレッド + スリッページ込みで TOPIX500 の流動銘柄で保守的な値)
- 戦略(Top N) と 母集団平均(pool) は能動売買扱いでコスト差し引き
- TOPIX 指数はパッシブベンチマークとしてコスト差し引きしない

Usage:
  .venv/bin/python scripts/apply_costs.py --input data/backtest_multi_all_90d.json --cost 0.2
"""
import argparse
import json
from pathlib import Path


def apply_cost_to_run(run: dict, cost_pct: float) -> dict:
    top = run.get("top", [])
    top_gross = [t["future_return_pct"] for t in top if t.get("future_return_pct") is not None]
    top_net = [g - cost_pct for g in top_gross]

    s = run.get("summary", {})
    gross_top = s.get("avg_return_top_pct")
    gross_pool = s.get("avg_return_pool_pct")
    topix_ret = s.get("topix_return_pct")

    net_top = round(gross_top - cost_pct, 2) if gross_top is not None else None
    net_pool = round(gross_pool - cost_pct, 2) if gross_pool is not None else None
    win_rate_net = round(sum(1 for r in top_net if r > 0) / len(top_net) * 100, 2) if top_net else None
    excess_topix_net = round(net_top - topix_ret, 2) if (net_top is not None and topix_ret is not None) else None
    excess_pool_net = round(net_top - net_pool, 2) if (net_top is not None and net_pool is not None) else None

    s["cost_roundtrip_pct"] = cost_pct
    s["avg_return_top_net_pct"] = net_top
    s["avg_return_pool_net_pct"] = net_pool
    s["win_rate_top_net_pct"] = win_rate_net
    s["excess_vs_topix_net_pct"] = excess_topix_net
    s["excess_vs_pool_net_pct"] = excess_pool_net
    return run


def main(input_path: Path, cost_pct: float, output_path: Path | None = None) -> None:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    for r in runs:
        apply_cost_to_run(r, cost_pct)

    excess_net = [r["summary"].get("excess_vs_topix_net_pct") for r in runs if r["summary"].get("excess_vs_topix_net_pct") is not None]
    data["cost_roundtrip_pct"] = cost_pct
    data["avg_excess_vs_topix_net"] = round(sum(excess_net) / len(excess_net), 4) if excess_net else None

    # レポート表示
    print(f"\n{'=' * 80}")
    print(f"取引コスト {cost_pct}% 適用後サマリー: {input_path.name}")
    print("=" * 80)
    print(f"{'基準日':<12} {'Top gross':>10} {'Top net':>10} {'TOPIX':>8} {'超過 gross':>11} {'超過 net':>10} {'勝率 net':>10}")
    for r in runs:
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
    if excess_net:
        avg = sum(excess_net) / len(excess_net)
        win = sum(1 for e in excess_net if e > 0)
        print(f"\n平均超過リターン net (vs TOPIX): {avg:+.2f}%")
        print(f"TOPIX超過した期数 net: {win}/{len(excess_net)}")

    out = output_path or input_path.with_name(input_path.stem + "_with_costs.json")
    with out.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n→ 保存: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True, help="backtest_multi_*.json のパス")
    parser.add_argument("--cost", type=float, default=0.2, help="往復コスト (%) デフォルト0.2")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    input_p = Path(args.input)
    output_p = Path(args.output) if args.output else None
    main(input_p, args.cost, output_p)
