"""β調整後 α (真の超過リターン) 分析

動機: raw 超過リターン は「戦略スキル(α)」と「市場感応度(β)」が混ざっている。
強気相場では高β銘柄が自動的に TOPIX 超過するので、raw の値を鵜呑みにすると
スキルを過大評価する恐れがある。CAPM の考え方で α を分離する。

定義:
  actual_return(h) = α(h) + β × topix_return(h)
  → α(h) = actual_return(h) - β × topix_return(h)

β 推定: 基準日前 180 営業日の日次対数リターンで stock を TOPIX にレグレッション
  β = cov(r_stock, r_topix) / var(r_topix)

Usage:
  .venv/bin/python scripts/backtest_alpha.py --input data/backtest_multi_all_90d.json
"""
import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import jquants  # noqa: E402


HOLDING_DAYS = [30, 60, 90, 180]
BETA_WINDOW_DAYS = 260  # 営業日200ちょいを確保したいので暦日260日


def _iso(d: date) -> str:
    return d.isoformat()


def daily_log_returns(bars: list[dict], close_key: str) -> list[tuple[str, float]]:
    """(date, log_return) 列を返す"""
    sorted_b = sorted(bars, key=lambda b: b.get("Date", ""))
    out = []
    prev = None
    for b in sorted_b:
        c = b.get(close_key)
        if c is None or c <= 0:
            prev = None
            continue
        if prev is not None and prev > 0:
            out.append((b["Date"], math.log(c / prev)))
        prev = c
    return out


def compute_beta(stock_returns: list[tuple[str, float]], topix_returns: list[tuple[str, float]]) -> float | None:
    """日付マッチした日次リターンで単純 OLS の β を返す"""
    topix_map = dict(topix_returns)
    pairs = [(s, topix_map[d]) for d, s in stock_returns if d in topix_map]
    if len(pairs) < 30:
        return None
    rs = [p[0] for p in pairs]
    rm = [p[1] for p in pairs]
    mean_m = sum(rm) / len(rm)
    mean_s = sum(rs) / len(rs)
    cov = sum((rs[i] - mean_s) * (rm[i] - mean_m) for i in range(len(pairs))) / len(pairs)
    var_m = sum((x - mean_m) ** 2 for x in rm) / len(rm)
    if var_m == 0:
        return None
    return cov / var_m


def compute_future_returns(bars_future: list[dict], base_date: date, entry_price: float, holding_list: list[int]) -> dict[int, float | None]:
    out = {}
    cut_base = _iso(base_date)
    future = sorted([b for b in bars_future if b.get("Date", "") > cut_base], key=lambda b: b["Date"])
    for h in holding_list:
        cut = _iso(base_date + timedelta(days=h))
        upto = [b for b in future if b["Date"] <= cut]
        if upto and entry_price:
            exit_p = upto[-1].get("AdjC")
            out[h] = (exit_p / entry_price - 1) * 100 if exit_p else None
        else:
            out[h] = None
    return out


def fetch_topix_returns(base_date: date, holding_list: list[int]) -> tuple[dict[int, float | None], list[tuple[str, float]]]:
    """未来リターン & 過去日次リターン"""
    past_start = base_date - timedelta(days=BETA_WINDOW_DAYS)
    future_end = base_date + timedelta(days=max(holding_list) + 14)

    past_bars = jquants._get("/indices/bars/daily/topix", {
        "from": past_start.strftime("%Y%m%d"),
        "to": base_date.strftime("%Y%m%d"),
    }).get("data", [])
    jquants.throttled_sleep(0.2)
    future_bars = jquants._get("/indices/bars/daily/topix", {
        "from": base_date.strftime("%Y%m%d"),
        "to": future_end.strftime("%Y%m%d"),
    }).get("data", [])
    jquants.throttled_sleep(0.2)

    past_rets = daily_log_returns(past_bars, "C")

    cut_base = _iso(base_date)
    future_sorted = sorted([b for b in future_bars if b.get("Date", "") >= cut_base], key=lambda b: b["Date"])
    if not future_sorted:
        return {h: None for h in holding_list}, past_rets
    entry = future_sorted[0]["C"]
    out = {}
    for h in holding_list:
        cut = _iso(base_date + timedelta(days=h))
        upto = [b for b in future_sorted if b.get("Date", "") <= cut]
        out[h] = (upto[-1]["C"] / entry - 1) * 100 if upto else None
    return out, past_rets


def main(input_path: Path, cost_pct: float) -> None:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    print(f"入力: {input_path.name} ({len(runs)}期)")
    print(f"β推定: 基準日前 {BETA_WINDOW_DAYS}暦日 (≒180営業日) の日次対数リターン")
    print(f"保有期間: {HOLDING_DAYS}日")

    per_period = []
    for run in runs:
        base_date = date.fromisoformat(run["base_date"])
        top = run.get("top", [])
        print(f"\n--- 基準日 {base_date} ({len(top)}銘柄) ---")

        topix_fwd, topix_past = fetch_topix_returns(base_date, HOLDING_DAYS)
        if not topix_past:
            print("  TOPIX 過去取得失敗、スキップ")
            continue
        print(f"  TOPIX fwd: {topix_fwd}")

        stocks_data = []
        for t in top:
            code = t["code"]
            entry_price = t.get("entry_price")
            if not entry_price:
                continue
            past_start = base_date - timedelta(days=BETA_WINDOW_DAYS)
            future_end = base_date + timedelta(days=max(HOLDING_DAYS) + 14)
            try:
                bars = jquants.get_daily_bars(code, past_start, future_end)
            except Exception as e:
                print(f"    skip {code}: {e}")
                continue
            jquants.throttled_sleep(0.2)

            past_bars = [b for b in bars if b.get("Date", "") <= _iso(base_date)]
            stock_past = daily_log_returns(past_bars, "AdjC")
            beta = compute_beta(stock_past, topix_past)

            rets = compute_future_returns(bars, base_date, entry_price, HOLDING_DAYS)
            print(f"    {code} {t['name'][:10]:10s} β={beta if beta is None else round(beta,2):>5} rets={rets}")
            stocks_data.append({"code": code, "name": t["name"], "beta": beta, "returns": rets})

        # ポートフォリオα計算 (β は等加重平均 = portfolio β)
        summary = {"base_date": run["base_date"], "topix_fwd": topix_fwd, "holding_stats": {}}
        betas = [s["beta"] for s in stocks_data if s["beta"] is not None]
        port_beta = sum(betas) / len(betas) if betas else None
        summary["portfolio_beta"] = round(port_beta, 3) if port_beta is not None else None
        print(f"  ポートフォリオ平均 β = {summary['portfolio_beta']}")

        for h in HOLDING_DAYS:
            rets = [s["returns"].get(h) for s in stocks_data if s["returns"].get(h) is not None]
            indiv_betas = [s["beta"] for s in stocks_data if s["returns"].get(h) is not None and s["beta"] is not None]
            if not rets:
                continue
            gross_avg = sum(rets) / len(rets)
            net_avg = gross_avg - cost_pct
            topix_h = topix_fwd.get(h)

            # 個別銘柄ごとに α_i = r_i - β_i × topix を計算して平均
            alphas = []
            for s in stocks_data:
                r = s["returns"].get(h)
                b = s["beta"]
                if r is None or b is None or topix_h is None:
                    continue
                alpha_i = r - b * topix_h
                alphas.append(alpha_i)
            alpha_gross = sum(alphas) / len(alphas) if alphas else None
            alpha_net = alpha_gross - cost_pct if alpha_gross is not None else None
            raw_excess_net = net_avg - topix_h if topix_h is not None else None

            summary["holding_stats"][h] = {
                "portfolio_return_net": round(net_avg, 2),
                "topix_return": round(topix_h, 2) if topix_h is not None else None,
                "raw_excess_net": round(raw_excess_net, 2) if raw_excess_net is not None else None,
                "alpha_net": round(alpha_net, 2) if alpha_net is not None else None,
                "alpha_stocks_used": len(alphas),
            }
        per_period.append(summary)

    # 保有期間別の集計
    print("\n\n" + "=" * 110)
    print(f"β調整後α 分析 (net = 往復{cost_pct}%差引)")
    print("=" * 110)
    print(f"\n{'保有':>5} {'Top net':>10} {'TOPIX':>8} {'raw 超過':>10} {'α (β調整後)':>14} {'α vs raw':>10} {'port β':>8}")
    agg = {}
    for h in HOLDING_DAYS:
        rows = [p["holding_stats"].get(h) for p in per_period if p["holding_stats"].get(h)]
        betas_all = [p["portfolio_beta"] for p in per_period if p["portfolio_beta"] is not None]
        if not rows:
            continue
        net_avg = sum(r["portfolio_return_net"] for r in rows) / len(rows)
        topix_avg = sum(r["topix_return"] for r in rows if r["topix_return"] is not None) / len(rows)
        raw_avg = sum(r["raw_excess_net"] for r in rows if r["raw_excess_net"] is not None) / len(rows)
        alpha_avg = sum(r["alpha_net"] for r in rows if r["alpha_net"] is not None) / len(rows)
        beta_avg = sum(betas_all) / len(betas_all) if betas_all else None

        agg[h] = {
            "top_net_avg": round(net_avg, 2),
            "topix_avg": round(topix_avg, 2),
            "raw_excess_net_avg": round(raw_avg, 2),
            "alpha_net_avg": round(alpha_avg, 2),
            "portfolio_beta_avg": round(beta_avg, 3) if beta_avg is not None else None,
        }
        print(
            f"{h:>3}d "
            f"{net_avg:>8.2f}% "
            f"{topix_avg:>6.2f}% "
            f"{raw_avg:>8.2f}% "
            f"{alpha_avg:>12.2f}% "
            f"{(alpha_avg - raw_avg):>8.2f}% "
            f"{(beta_avg or 0):>7.2f}"
        )

    out = input_path.with_name(input_path.stem + "_alpha.json")
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "cost_roundtrip_pct": cost_pct,
            "beta_window_days": BETA_WINDOW_DAYS,
            "holding_days_tested": HOLDING_DAYS,
            "per_period": per_period,
            "aggregate_by_holding": agg,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n→ 保存: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--cost", type=float, default=0.2)
    args = parser.parse_args()
    main(Path(args.input), args.cost)
