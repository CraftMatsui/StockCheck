"""保有期間感度テスト: 既存バックテストの top10 選定を再利用し、
30/60/90/180 日の net リターンを比較する

設計思想:
- 再スクリーニングしない (score が同じなので top10 選定は不変)
- future バーと TOPIX だけ再取得 → API コール最小化
- 目的: 90 日保有が最適か、過学習で偶然性能が出ていないかの OOS チェック

Usage:
  .venv/bin/python scripts/backtest_sensitivity.py --input data/backtest_multi_all_90d.json
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import jquants  # noqa: E402


HOLDING_DAYS = [30, 60, 90, 180]


def _iso(d: date) -> str:
    return d.isoformat()


def compute_returns_at_holdings(code: str, base_date: date, entry_price: float, holding_list: list[int]) -> dict[int, float | None]:
    max_hold = max(holding_list)
    end = base_date + timedelta(days=max_hold + 14)
    try:
        bars = jquants.get_daily_bars(code, base_date, end)
    except Exception as e:
        print(f"    skip {code}: {e}")
        return {h: None for h in holding_list}
    jquants.throttled_sleep(0.2)

    cut_base = _iso(base_date)
    future = sorted([b for b in bars if b.get("Date", "") > cut_base], key=lambda b: b["Date"])

    out = {}
    for h in holding_list:
        cut = _iso(base_date + timedelta(days=h))
        upto = [b for b in future if b["Date"] <= cut]
        if upto and entry_price:
            exit_p = upto[-1].get("AdjC")
            out[h] = round((exit_p / entry_price - 1) * 100, 2) if exit_p else None
        else:
            out[h] = None
    return out


def topix_returns_at_holdings(base_date: date, holding_list: list[int]) -> dict[int, float | None]:
    max_hold = max(holding_list)
    end = base_date + timedelta(days=max_hold + 14)
    try:
        data = jquants._get("/indices/bars/daily/topix", {
            "from": base_date.strftime("%Y%m%d"),
            "to": end.strftime("%Y%m%d"),
        }).get("data", [])
    except Exception as e:
        print(f"  TOPIX skip: {e}")
        return {h: None for h in holding_list}

    data = sorted(data, key=lambda b: b.get("Date", ""))
    if not data:
        return {h: None for h in holding_list}
    entry = data[0]["C"]

    out = {}
    for h in holding_list:
        cut = _iso(base_date + timedelta(days=h))
        upto = [b for b in data if b.get("Date", "") <= cut]
        if upto:
            out[h] = round((upto[-1]["C"] / entry - 1) * 100, 2)
        else:
            out[h] = None
    return out


def main(input_path: Path, cost_pct: float) -> None:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    print(f"\n入力: {input_path.name} ({len(runs)}期)")
    print(f"保有期間: {HOLDING_DAYS}日")
    print(f"取引コスト: 往復 {cost_pct}%")

    per_period_results = []  # list of dict per base_date
    for run in runs:
        base_date = date.fromisoformat(run["base_date"])
        top = run.get("top", [])
        print(f"\n--- 基準日 {base_date} ({len(top)}銘柄) ---")

        # TOPIX
        topix_map = topix_returns_at_holdings(base_date, HOLDING_DAYS)
        jquants.throttled_sleep(0.2)
        print(f"  TOPIX: {topix_map}")

        # 各 top stock の未来リターン
        top_returns_by_h: dict[int, list[float]] = {h: [] for h in HOLDING_DAYS}
        for t in top:
            code = t["code"]
            entry_price = t.get("entry_price")
            if not entry_price:
                continue
            rets = compute_returns_at_holdings(code, base_date, entry_price, HOLDING_DAYS)
            print(f"    {code} {t['name'][:10]:10s} {rets}")
            for h, v in rets.items():
                if v is not None:
                    top_returns_by_h[h].append(v)

        # 集計
        per_run = {"base_date": run["base_date"], "topix": topix_map, "top_net_avg": {}, "top_gross_avg": {}, "excess_net": {}, "win_rate_net": {}}
        for h in HOLDING_DAYS:
            rets = top_returns_by_h[h]
            if not rets:
                continue
            gross = sum(rets) / len(rets)
            net = gross - cost_pct
            net_rets = [r - cost_pct for r in rets]
            win = sum(1 for r in net_rets if r > 0) / len(net_rets) * 100
            topix = topix_map.get(h)
            per_run["top_gross_avg"][h] = round(gross, 2)
            per_run["top_net_avg"][h] = round(net, 2)
            per_run["win_rate_net"][h] = round(win, 2)
            per_run["excess_net"][h] = round(net - topix, 2) if topix is not None else None
        per_period_results.append(per_run)

    # 時系列 → 保有期間別集計
    print("\n\n" + "=" * 100)
    print(f"保有期間感度サマリー (net = 往復{cost_pct}%差引、TOPIX はそのまま)")
    print("=" * 100)
    print(f"\n{'保有':>6} {'Top net 平均':>14} {'TOPIX 平均':>12} {'超過 net 平均':>14} {'勝率 net 平均':>14} {'期間分散 (std)':>16}")

    agg = {}
    for h in HOLDING_DAYS:
        tops = [r["top_net_avg"].get(h) for r in per_period_results if r["top_net_avg"].get(h) is not None]
        tops_gross = [r["top_gross_avg"].get(h) for r in per_period_results if r["top_gross_avg"].get(h) is not None]
        topixs = [r["topix"].get(h) for r in per_period_results if r["topix"].get(h) is not None]
        excess = [r["excess_net"].get(h) for r in per_period_results if r["excess_net"].get(h) is not None]
        wins = [r["win_rate_net"].get(h) for r in per_period_results if r["win_rate_net"].get(h) is not None]

        if not tops:
            continue
        avg_top = sum(tops) / len(tops)
        avg_topix = sum(topixs) / len(topixs) if topixs else None
        avg_excess = sum(excess) / len(excess) if excess else None
        avg_win = sum(wins) / len(wins) if wins else None
        # 期間分散
        if len(excess) >= 2:
            mean = sum(excess) / len(excess)
            var = sum((x - mean) ** 2 for x in excess) / len(excess)
            std = var ** 0.5
        else:
            std = None
        win_periods = sum(1 for e in excess if e > 0)

        agg[h] = {
            "top_net_avg": round(avg_top, 2),
            "top_gross_avg": round(sum(tops_gross) / len(tops_gross), 2) if tops_gross else None,
            "topix_avg": round(avg_topix, 2) if avg_topix is not None else None,
            "excess_net_avg": round(avg_excess, 2) if avg_excess is not None else None,
            "win_rate_net_avg": round(avg_win, 2) if avg_win is not None else None,
            "excess_net_std": round(std, 2) if std is not None else None,
            "topix_win_periods": f"{win_periods}/{len(excess)}",
        }
        print(
            f"{h:>4}d "
            f"{avg_top:>12.2f}% "
            f"{(avg_topix or 0):>10.2f}% "
            f"{(avg_excess or 0):>12.2f}% "
            f"{(avg_win or 0):>12.2f}% "
            f"{(std or 0):>14.2f} "
            f"({win_periods}/{len(excess)}期超過)"
        )

    out = input_path.with_name(input_path.stem + "_sensitivity.json")
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "cost_roundtrip_pct": cost_pct,
            "holding_days_tested": HOLDING_DAYS,
            "per_period": per_period_results,
            "aggregate_by_holding": agg,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n→ 保存: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--cost", type=float, default=0.2)
    args = parser.parse_args()
    main(Path(args.input), args.cost)
