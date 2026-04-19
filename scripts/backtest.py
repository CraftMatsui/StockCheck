"""バックテスト: 過去の基準日時点でスクリーニングを走らせ、その後のリターンを計測

設計上の制約 (レポートに注記すべき):
- サバイバーシップバイアス: 現在のTOPIX500構成銘柄のみ対象 (過去の除外銘柄は含まれない)
- ファンダ指標は DiscDate ≤ 基準日 でフィルタしてルックアヘッドバイアスを回避
- AIエージェント部分は検証不可のため、機械的スクリーニング score_stock() のみ検証

Usage:
  .venv/bin/python scripts/backtest.py --base 2025-10-17 --days 90 --scale core30
"""
import json
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import jquants  # noqa: E402
from lib.technical import compute_price_metrics  # noqa: E402
from lib.scoring import compute_fundamentals, score_stock  # noqa: E402


SCALE_PRESETS = {
    "core30": {"TOPIX Core30"},
    "large70": {"TOPIX Core30", "TOPIX Large70"},
    "all": {"TOPIX Core30", "TOPIX Large70", "TOPIX Mid400"},
}


def _code4(code5: str) -> str:
    return code5[:-1] if len(code5) == 5 else code5


def _iso(d: date) -> str:
    return d.isoformat()


def filter_summary_by_date(summary: list[dict], cutoff: date) -> list[dict]:
    """DiscDate ≤ cutoff の決算サマリーのみ残す (ルックアヘッド防止)"""
    result = []
    for s in summary:
        disc = s.get("DiscDate")
        if not disc:
            continue
        try:
            d = date.fromisoformat(disc)
        except ValueError:
            continue
        if d <= cutoff:
            result.append(s)
    return result


def get_topix_return(base_date: date, holding_days: int) -> float | None:
    """TOPIX指数の期間リターン (%)"""
    end = base_date + timedelta(days=holding_days + 14)
    try:
        data = jquants._get("/indices/bars/daily/topix", {
            "from": base_date.strftime("%Y%m%d"),
            "to": end.strftime("%Y%m%d"),
        }).get("data", [])
    except Exception as e:
        print(f"  [warn] TOPIX取得失敗: {e}")
        return None
    data = sorted(data, key=lambda b: b.get("Date", ""))
    cut = _iso(base_date + timedelta(days=holding_days))
    upto = [b for b in data if b.get("Date", "") <= cut]
    if len(data) < 2 or not upto:
        return None
    entry = data[0]["C"]
    exit_ = upto[-1]["C"]
    return round((exit_ / entry - 1) * 100, 2)


def run_backtest(base_date: date, holding_days: int, top_n: int, scale_name: str, cost_roundtrip_pct: float = 0.2) -> dict:
    pool_scales = SCALE_PRESETS.get(scale_name, SCALE_PRESETS["core30"])
    print(f"\n=== バックテスト ===")
    print(f"基準日: {base_date}  保有期間: {holding_days}日  上位: {top_n}銘柄  母集団: {scale_name}")

    all_eq = jquants.list_all_equities()
    pool = [e for e in all_eq if e.get("ScaleCat") in pool_scales]
    print(f"母集団: {len(pool)}銘柄")

    start = base_date - timedelta(days=400)
    future_end = base_date + timedelta(days=holding_days + 14)

    enriched = []
    for i, eq in enumerate(pool, 1):
        code = _code4(eq["Code"])
        name = eq.get("CoName", "")

        if i % 25 == 0 or i == len(pool):
            print(f"  [{i}/{len(pool)}] {code} {name}")

        try:
            bars_all = jquants.get_daily_bars(code, start, future_end)
            jquants.throttled_sleep(0.2)
            summary_all = jquants.get_financial_summary(code)
            jquants.throttled_sleep(0.2)
        except Exception as e:
            print(f"  skip {code}: {e}")
            continue

        cut = _iso(base_date)
        bars_past = [b for b in bars_all if b.get("Date", "9999") <= cut]
        bars_future = [b for b in bars_all if b.get("Date", "") > cut]

        if len(bars_past) < 30:
            continue

        price_m = compute_price_metrics(bars_past)
        if not price_m:
            continue

        summary_past = filter_summary_by_date(summary_all, base_date)
        fund_m = compute_fundamentals(summary_past, price_m.get("current"))
        score = score_stock(price_m, fund_m)

        # 未来リターン
        cut_future = _iso(base_date + timedelta(days=holding_days))
        future_upto = [b for b in bars_future if b.get("Date", "") <= cut_future]
        entry_price = price_m.get("current")
        if future_upto and entry_price:
            exit_price = future_upto[-1].get("AdjC")
            future_return = round((exit_price / entry_price - 1) * 100, 2) if exit_price else None
        else:
            future_return = None

        enriched.append({
            "code": code,
            "name": name,
            "sector17": eq.get("S17Nm", ""),
            "score": score,
            "entry_price": entry_price,
            "future_return_pct": future_return,
            "per": fund_m.get("per"),
            "pbr": fund_m.get("pbr"),
            "roe": fund_m.get("roe"),
            "pct_from_high": price_m.get("pct_from_high"),
            "mom_3m_pct": price_m.get("mom_3m_pct"),
            "turnover_20d_avg": price_m.get("turnover_20d_avg"),
        })

    enriched.sort(key=lambda x: x["score"], reverse=True)
    top = enriched[:top_n]
    all_returns = [e["future_return_pct"] for e in enriched if e["future_return_pct"] is not None]
    top_returns = [e["future_return_pct"] for e in top if e["future_return_pct"] is not None]

    avg_top = sum(top_returns) / len(top_returns) if top_returns else None
    avg_all = sum(all_returns) / len(all_returns) if all_returns else None
    win_rate_top = sum(1 for r in top_returns if r > 0) / len(top_returns) * 100 if top_returns else None

    topix_ret = get_topix_return(base_date, holding_days)
    excess_vs_topix = round(avg_top - topix_ret, 2) if (avg_top is not None and topix_ret is not None) else None
    excess_vs_pool = round(avg_top - avg_all, 2) if (avg_top is not None and avg_all is not None) else None

    # 取引コスト差し引き: 往復 cost_roundtrip_pct% を戦略・母集団に適用、TOPIX は passive で差し引きなし
    net_top = round(avg_top - cost_roundtrip_pct, 2) if avg_top is not None else None
    net_pool = round(avg_all - cost_roundtrip_pct, 2) if avg_all is not None else None
    top_returns_net = [r - cost_roundtrip_pct for r in top_returns]
    win_rate_top_net = sum(1 for r in top_returns_net if r > 0) / len(top_returns_net) * 100 if top_returns_net else None
    excess_vs_topix_net = round(net_top - topix_ret, 2) if (net_top is not None and topix_ret is not None) else None
    excess_vs_pool_net = round(net_top - net_pool, 2) if (net_top is not None and net_pool is not None) else None

    summary = {
        "avg_return_top_pct": round(avg_top, 2) if avg_top is not None else None,
        "avg_return_pool_pct": round(avg_all, 2) if avg_all is not None else None,
        "win_rate_top_pct": round(win_rate_top, 2) if win_rate_top is not None else None,
        "topix_return_pct": topix_ret,
        "excess_vs_topix_pct": excess_vs_topix,
        "excess_vs_pool_pct": excess_vs_pool,
        "cost_roundtrip_pct": cost_roundtrip_pct,
        "avg_return_top_net_pct": net_top,
        "avg_return_pool_net_pct": net_pool,
        "win_rate_top_net_pct": round(win_rate_top_net, 2) if win_rate_top_net is not None else None,
        "excess_vs_topix_net_pct": excess_vs_topix_net,
        "excess_vs_pool_net_pct": excess_vs_pool_net,
    }

    # 表示
    print(f"\n=== 結果: トップ{top_n}銘柄 ===")
    for t in top:
        ret = t["future_return_pct"]
        ret_s = f"{ret:+6.2f}%" if ret is not None else "  ---"
        print(
            f"  {t['code']} {t['name'][:12]:12s} "
            f"score={t['score']:5.1f} "
            f"PER={str(t['per']):>6s} 52wH={str(t['pct_from_high']):>5s}% "
            f"→ リターン={ret_s}"
        )
    print(f"\n📊 サマリー (gross / net: 往復{cost_roundtrip_pct}%差引)")
    print(f"  トップ{top_n}平均リターン:  gross={summary['avg_return_top_pct']}%  net={summary['avg_return_top_net_pct']}%")
    print(f"  母集団平均リターン:      gross={summary['avg_return_pool_pct']}%  net={summary['avg_return_pool_net_pct']}%")
    print(f"  トップ勝率:              gross={summary['win_rate_top_pct']}%  net={summary['win_rate_top_net_pct']}%")
    print(f"  TOPIXリターン:           {summary['topix_return_pct']}% (passive)")
    print(f"  超過リターン(vs TOPIX):  gross={summary['excess_vs_topix_pct']}%  net={summary['excess_vs_topix_net_pct']}%")
    print(f"  超過リターン(vs 母集団): gross={summary['excess_vs_pool_pct']}%  net={summary['excess_vs_pool_net_pct']}%")

    return {
        "base_date": _iso(base_date),
        "holding_days": holding_days,
        "top_n": top_n,
        "scale": scale_name,
        "pool_size": len(pool),
        "screened": len(enriched),
        "top": top,
        "summary": summary,
        "enriched_pool": enriched,  # 500銘柄全件（post-processフィルタ比較用）
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=str, default=None, help="基準日 YYYY-MM-DD (デフォルト: 180日前)")
    parser.add_argument("--days", type=int, default=90, help="保有期間 (日)")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--scale", type=str, default="core30", choices=list(SCALE_PRESETS.keys()))
    parser.add_argument("--cost", type=float, default=0.2, help="往復取引コスト (%) デフォルト0.2")
    args = parser.parse_args()

    base = date.fromisoformat(args.base) if args.base else (date.today() - timedelta(days=180))
    result = run_backtest(base, args.days, args.top_n, args.scale, cost_roundtrip_pct=args.cost)

    out = Path(__file__).resolve().parent.parent / "data" / f"backtest_{base}_{args.days}d_{args.scale}.json"
    out.parent.mkdir(exist_ok=True, parents=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n→ 保存: {out}")
