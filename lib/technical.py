"""テクニカル指標とライン計算のユーティリティ"""
from typing import Optional


def compute_price_metrics(bars: list[dict]) -> dict:
    """日足からテクニカル指標を計算。bars は古い順に並んだ J-Quants の /equities/bars/daily レスポンス"""
    if len(bars) < 30:
        return {}

    closes = [b["AdjC"] for b in bars if b.get("AdjC") is not None]
    highs = [b["AdjH"] for b in bars if b.get("AdjH") is not None]
    lows = [b["AdjL"] for b in bars if b.get("AdjL") is not None]
    vols = [b["AdjVo"] for b in bars if b.get("AdjVo") is not None]

    if len(closes) < 30:
        return {}

    current = closes[-1]
    high_52w = max(highs[-250:]) if len(highs) >= 250 else max(highs)
    low_52w = min(lows[-250:]) if len(lows) >= 250 else min(lows)

    vol_20 = sum(vols[-20:]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)
    vol_5 = sum(vols[-5:]) / 5 if len(vols) >= 5 else sum(vols) / len(vols)

    # 売買代金 = 調整後終値 × 調整後出来高 (直近20営業日平均、単位:円)
    turnovers = []
    for b in bars[-20:]:
        c = b.get("AdjC")
        v = b.get("AdjVo")
        if c is not None and v is not None:
            turnovers.append(c * v)
    turnover_20d_avg = sum(turnovers) / len(turnovers) if turnovers else None

    mom_3m = (current / closes[-63] - 1) * 100 if len(closes) >= 63 else None
    mom_1m = (current / closes[-21] - 1) * 100 if len(closes) >= 21 else None

    ma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
    ma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None

    trs = []
    for i in range(max(1, len(bars) - 14), len(bars)):
        hi = bars[i].get("AdjH")
        lo = bars[i].get("AdjL")
        pc = bars[i - 1].get("AdjC")
        if hi is None or lo is None or pc is None:
            continue
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    atr_14 = sum(trs) / len(trs) if trs else None

    return {
        "current": round(current, 1),
        "high_52w": round(high_52w, 1),
        "low_52w": round(low_52w, 1),
        "pct_from_high": round(current / high_52w * 100, 2) if high_52w else None,
        "pct_from_low": round(current / low_52w * 100, 2) if low_52w else None,
        "vol_5d_avg": round(vol_5, 0),
        "vol_20d_avg": round(vol_20, 0),
        "vol_ratio": round(vol_5 / vol_20, 2) if vol_20 else None,
        "mom_1m_pct": round(mom_1m, 2) if mom_1m is not None else None,
        "mom_3m_pct": round(mom_3m, 2) if mom_3m is not None else None,
        "ma_50": round(ma_50, 1) if ma_50 else None,
        "ma_200": round(ma_200, 1) if ma_200 else None,
        "above_ma50": current > ma_50 if ma_50 else None,
        "above_ma200": current > ma_200 if ma_200 else None,
        "atr_14": round(atr_14, 2) if atr_14 else None,
        "atr_pct": round(atr_14 / current * 100, 2) if atr_14 and current else None,
        "turnover_20d_avg": round(turnover_20d_avg, 0) if turnover_20d_avg else None,
    }


def compute_lines(bars: list[dict]) -> dict:
    """利確ラインと損切りラインを機械的に算出

    - 利確: 52週高値近辺(>=95%)なら +15%のブレイクを想定、それ以外は52週高値
    - 損切: MA200 と 現在値-ATR*2 のうち「現在値に近い方」(=より浅い方)
    """
    m = compute_price_metrics(bars)
    current = m.get("current")
    high_52w = m.get("high_52w")
    ma_200 = m.get("ma_200")
    atr_14 = m.get("atr_14")

    if not current:
        return {}

    # 利確
    if high_52w and current / high_52w >= 0.95:
        target = current * 1.15
    elif high_52w:
        target = high_52w
    else:
        target = current * 1.15  # フォールバック

    # 損切: 「深い方」=より低い方を採用
    # 理由: 浅いストップはノイズで損切り狩りされやすく、トレンドフォローと相性が悪い
    # ATR*2 は最低限のボラティリティマージン、MA200 がさらに下なら MA200 を尊重
    candidates = []
    if ma_200 and ma_200 < current:  # 上昇トレンド中のみMA200を下値サポート扱い
        candidates.append(ma_200)
    if atr_14:
        candidates.append(current - atr_14 * 2)
    if candidates:
        stop = min(candidates)  # 深い方=より低い方を採用
    else:
        stop = current * 0.9  # フォールバック -10%

    # 異常値ガード
    if stop >= current:
        stop = current * 0.9
    if target <= current:
        target = current * 1.15

    return {
        "target_price": round(target, 0),
        "stop_loss": round(stop, 0),
        "current": current,
        "target_pct": round((target / current - 1) * 100, 2),
        "stop_pct": round((stop / current - 1) * 100, 2),
    }
