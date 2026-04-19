"""銘柄スコアリングとファンダメンタル指標計算のロジック

screen_candidates.py と backtest.py から共通利用される。
"""

TOPIX500_SCALES = {"TOPIX Core30", "TOPIX Large70", "TOPIX Mid400"}

# 実運用で個人投資家が1銘柄あたり100-300万円投じる想定。値動きへの影響を1%以内に抑えたい
LIQUIDITY_THRESHOLD_YEN = 3e8  # 3億円

# sector17で1ポートフォリオあたり同業種max3銘柄まで。分散効果を確保
SECTOR_CAP_DEFAULT = 3


def is_topix500(scale_cat: str) -> bool:
    return scale_cat in TOPIX500_SCALES


def passes_liquidity_filter(price: dict, threshold_yen: float = LIQUIDITY_THRESHOLD_YEN) -> bool:
    """直近20営業日平均売買代金が threshold_yen 以上ならTrue。データ欠損は保守的にFalse"""
    t = price.get("turnover_20d_avg")
    return t is not None and t >= threshold_yen


def select_with_sector_cap(
    candidates: list[dict],
    top_n: int,
    cap: int = SECTOR_CAP_DEFAULT,
    sector_key: str = "sector17",
    score_key: str = "score",
) -> list[dict]:
    """スコア降順で greedy に選択、同セクター cap 到達なら skip"""
    sorted_c = sorted(candidates, key=lambda x: x.get(score_key, 0), reverse=True)
    sector_count: dict[str, int] = {}
    result: list[dict] = []
    for c in sorted_c:
        sec = c.get(sector_key, "") or "(unknown)"
        if sector_count.get(sec, 0) >= cap:
            continue
        result.append(c)
        sector_count[sec] = sector_count.get(sec, 0) + 1
        if len(result) >= top_n:
            break
    return result


def _to_float(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def compute_fundamentals(summary: list[dict], current_price: float | None) -> dict:
    """財務サマリーからファンダ指標を計算。summary は古い順・実績値のあるFYレコード"""
    if not summary:
        return {}

    fys = [
        s for s in summary
        if s.get("CurPerType") == "FY"
        and s.get("EPS") not in (None, "")
        and s.get("NP") not in (None, "")
    ]
    fys.sort(key=lambda s: s.get("CurPerEn", ""))

    if not fys:
        return {}

    latest = fys[-1]
    eps = _to_float(latest.get("EPS"))
    bps = _to_float(latest.get("BPS"))
    np_ = _to_float(latest.get("NP"))
    eq = _to_float(latest.get("Eq"))
    ta = _to_float(latest.get("TA"))
    sales = _to_float(latest.get("Sales"))
    op = _to_float(latest.get("OP"))
    div = _to_float(latest.get("DivAnn"))
    eq_ratio = _to_float(latest.get("EqAR"))
    payout = _to_float(latest.get("PayoutRatioAnn"))

    prev_sales = None
    prev_np = None
    if len(fys) >= 2:
        prev = fys[-2]
        prev_sales = _to_float(prev.get("Sales"))
        prev_np = _to_float(prev.get("NP"))

    per = (current_price / eps) if (current_price and eps and eps > 0) else None
    pbr = (current_price / bps) if (current_price and bps and bps > 0) else None
    roe = (np_ / eq * 100) if (np_ is not None and eq and eq > 0) else None
    roa = (np_ / ta * 100) if (np_ is not None and ta and ta > 0) else None
    div_yield = (div / current_price * 100) if (current_price and div) else None
    op_margin = (op / sales * 100) if (op is not None and sales and sales > 0) else None
    sales_growth = ((sales / prev_sales - 1) * 100) if (sales and prev_sales and prev_sales > 0) else None
    np_growth = ((np_ / prev_np - 1) * 100) if (np_ is not None and prev_np and prev_np > 0) else None

    return {
        "fy_end": latest.get("CurPerEn"),
        "disc_date": latest.get("DiscDate"),
        "per": round(per, 2) if per else None,
        "pbr": round(pbr, 2) if pbr else None,
        "roe": round(roe, 2) if roe is not None else None,
        "roa": round(roa, 2) if roa is not None else None,
        "eps": eps,
        "bps": bps,
        "div_annual": div,
        "div_yield": round(div_yield, 2) if div_yield else None,
        "payout_ratio": round(payout * 100, 2) if payout else None,
        "op_margin": round(op_margin, 2) if op_margin else None,
        "equity_ratio": round(eq_ratio * 100, 2) if eq_ratio else None,
        "sales_growth": round(sales_growth, 2) if sales_growth is not None else None,
        "np_growth": round(np_growth, 2) if np_growth is not None else None,
    }


def score_stock(price: dict, fund: dict) -> float:
    """バランス型スコア (高いほど魅力的)"""
    s = 0.0

    # ファンダ: 割安さ (低PERはバリュートラップ・PBR<0.3は事業毀損でペナルティ)
    per = fund.get("per")
    if per is not None and per > 0:
        if per < 5:
            s -= 5
        elif per < 30:
            s += max(0, 30 - per) / 3
    pbr = fund.get("pbr")
    if pbr is not None and pbr > 0:
        if pbr < 0.3:
            s -= 3
        elif pbr < 5:
            s += max(0, 5 - pbr)

    # ファンダ: 収益性
    if fund.get("roe") is not None:
        s += min(fund["roe"], 25) / 3
    if fund.get("op_margin") is not None:
        s += min(fund["op_margin"], 30) / 5
    # ファンダ: 成長性
    if fund.get("sales_growth") is not None:
        s += min(max(fund["sales_growth"], -10), 30) / 3
    # ファンダ: 配当
    if fund.get("div_yield"):
        s += min(fund["div_yield"], 6)
    # ファンダ: 財務健全性
    if fund.get("equity_ratio") and fund["equity_ratio"] > 30:
        s += 1

    # テクニカル: トレンド
    if price.get("above_ma50"):
        s += 2
    if price.get("above_ma200"):
        s += 2
    # テクニカル: 52週高値接近度 (85-98%スイート、>98%は過熱減点)
    pfh = price.get("pct_from_high")
    if pfh:
        if pfh > 98:
            s -= 2
        elif 85 <= pfh <= 98:
            s += 4
        elif 70 <= pfh < 85:
            s += 2
    # テクニカル: 出来高急増
    vr = price.get("vol_ratio")
    if vr and vr > 1.2:
        s += min((vr - 1) * 3, 5)
    # テクニカル: モメンタム
    m3 = price.get("mom_3m_pct")
    if m3 is not None:
        s += min(max(m3, -20), 30) / 5

    return round(s, 2)
