"""保存された enriched pool に複数フィルタ条件を適用して比較

前提: backtest.py で enriched_pool (500銘柄全件の future_return + turnover + sector17) が保存済み

比較条件:
  - baseline: フィルタなし、スコア上位10
  - +liquidity: turnover_20d_avg >= 3億円 を pass した中からスコア上位10
  - +sector-cap: 17業種ごとmax3銘柄、スコア上位10
  - +both: 両フィルタ適用後、スコア上位10 (ハードキャップ3)

Usage:
  .venv/bin/python scripts/apply_filters.py --input data/backtest_multi_all_90d.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.scoring import passes_liquidity_filter, select_with_sector_cap, LIQUIDITY_THRESHOLD_YEN, SECTOR_CAP_DEFAULT  # noqa: E402


CONFIGS = {
    "baseline": {"liquidity": False, "sector_cap": False},
    "liquidity": {"liquidity": True, "sector_cap": False},
    "sector_cap": {"liquidity": False, "sector_cap": True},
    "both": {"liquidity": True, "sector_cap": True},
}


def select_top(pool: list[dict], liquidity: bool, sector_cap: bool, top_n: int = 10) -> list[dict]:
    # 流動性フィルタ
    filtered = pool
    if liquidity:
        filtered = [p for p in filtered if passes_liquidity_filter({"turnover_20d_avg": p.get("turnover_20d_avg")})]
    # 選定
    if sector_cap:
        return select_with_sector_cap(filtered, top_n=top_n, cap=SECTOR_CAP_DEFAULT)
    filtered_sorted = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)
    return filtered_sorted[:top_n]


def aggregate_top(top: list[dict], cost_pct: float, topix_ret: float | None) -> dict:
    rets = [t["future_return_pct"] for t in top if t.get("future_return_pct") is not None]
    if not rets:
        return {}
    gross = sum(rets) / len(rets)
    net = gross - cost_pct
    net_rets = [r - cost_pct for r in rets]
    win = sum(1 for r in net_rets if r > 0) / len(net_rets) * 100
    excess_net = (net - topix_ret) if topix_ret is not None else None
    return {
        "top_n": len(top),
        "avg_gross_pct": round(gross, 2),
        "avg_net_pct": round(net, 2),
        "win_rate_net_pct": round(win, 2),
        "excess_net_vs_topix_pct": round(excess_net, 2) if excess_net is not None else None,
        "sectors": sorted(set(t.get("sector17", "") for t in top)),
    }


def main(input_path: Path, cost_pct: float) -> None:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    print(f"入力: {input_path.name} ({len(runs)}期)")
    if not runs or "enriched_pool" not in runs[0]:
        print("ERROR: enriched_pool が無い。backtest 再実行が必要（改修版）。")
        sys.exit(1)

    results_by_config: dict[str, list[dict]] = {k: [] for k in CONFIGS}
    for run in runs:
        base_date = run["base_date"]
        pool = run.get("enriched_pool", [])
        topix_ret = run["summary"].get("topix_return_pct")
        print(f"\n基準日 {base_date}: pool={len(pool)}銘柄 TOPIX={topix_ret}%")
        for cfg_name, cfg in CONFIGS.items():
            top = select_top(pool, cfg["liquidity"], cfg["sector_cap"])
            agg = aggregate_top(top, cost_pct, topix_ret)
            agg["base_date"] = base_date
            agg["config"] = cfg_name
            agg["codes"] = [t["code"] for t in top]
            agg["sector_counts"] = {}
            for t in top:
                sec = t.get("sector17", "") or "(unknown)"
                agg["sector_counts"][sec] = agg["sector_counts"].get(sec, 0) + 1
            results_by_config[cfg_name].append(agg)
            print(f"  [{cfg_name:11s}] top{agg['top_n']} net={agg['avg_net_pct']}% 超過={agg['excess_net_vs_topix_pct']}% 業種数={len(agg['sectors'])}")

    # 集計
    print("\n\n" + "=" * 100)
    print(f"フィルタ条件比較 (n={len(runs)}期、コスト往復{cost_pct}%差引後)")
    print("=" * 100)
    print(f"\n{'config':<12} {'Top net 平均':>14} {'超過 net 平均':>14} {'勝率 net 平均':>14} {'超過>0期数':>12}")
    summary_by_cfg = {}
    for cfg_name, rows in results_by_config.items():
        if not rows:
            continue
        nets = [r["avg_net_pct"] for r in rows if r.get("avg_net_pct") is not None]
        excesses = [r["excess_net_vs_topix_pct"] for r in rows if r.get("excess_net_vs_topix_pct") is not None]
        wins_indiv = [r["win_rate_net_pct"] for r in rows if r.get("win_rate_net_pct") is not None]
        net_avg = sum(nets) / len(nets) if nets else None
        excess_avg = sum(excesses) / len(excesses) if excesses else None
        win_avg = sum(wins_indiv) / len(wins_indiv) if wins_indiv else None
        win_periods = sum(1 for e in excesses if e > 0)
        summary_by_cfg[cfg_name] = {
            "avg_net_pct": round(net_avg, 2) if net_avg is not None else None,
            "avg_excess_net_pct": round(excess_avg, 2) if excess_avg is not None else None,
            "avg_win_rate_net_pct": round(win_avg, 2) if win_avg is not None else None,
            "topix_beat_periods": f"{win_periods}/{len(excesses)}",
        }
        print(
            f"{cfg_name:<12} "
            f"{(net_avg or 0):>12.2f}% "
            f"{(excess_avg or 0):>12.2f}% "
            f"{(win_avg or 0):>12.2f}% "
            f"{win_periods}/{len(excesses)} 期"
        )

    # ベースラインとの差分
    print("\n[baseline比較]")
    base_excess = summary_by_cfg["baseline"]["avg_excess_net_pct"]
    for cfg_name, s in summary_by_cfg.items():
        if cfg_name == "baseline":
            continue
        delta = s["avg_excess_net_pct"] - base_excess
        sign = "+" if delta >= 0 else ""
        print(f"  {cfg_name:<12}: 超過 net {s['avg_excess_net_pct']:+.2f}% (baseline比 {sign}{delta:.2f}%)")

    out = input_path.with_name(input_path.stem + "_filters.json")
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "cost_roundtrip_pct": cost_pct,
            "liquidity_threshold_yen": LIQUIDITY_THRESHOLD_YEN,
            "sector_cap": SECTOR_CAP_DEFAULT,
            "summary_by_config": summary_by_cfg,
            "per_period_by_config": results_by_config,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n→ 保存: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--cost", type=float, default=0.2)
    args = parser.parse_args()
    main(Path(args.input), args.cost)
