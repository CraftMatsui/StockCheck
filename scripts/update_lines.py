"""保有銘柄 + 監視銘柄 の利確/損切りラインを毎日更新するスクリプト

入力: Googleシートの holdings + watchlist
出力: Googleシートの lines タブ (code, target_price, stop_loss, updated_at)
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import jquants, sheets  # noqa: E402
from lib.technical import compute_lines  # noqa: E402


def main() -> None:
    holdings = sheets.list_holdings()
    watchlist = sheets.list_watchlist()

    codes = set()
    for h in holdings:
        c = str(h.get("code") or "").strip()
        if c:
            codes.add(c)
    for w in watchlist:
        c = str(w.get("code") or "").strip()
        if c:
            codes.add(c)

    if not codes:
        print("保有銘柄も監視銘柄も登録されていません。スキップ。")
        sheets.replace_all_lines([])
        return

    print(f"対象銘柄: {len(codes)}件 ({sorted(codes)})")

    today = date.today()
    start = today - timedelta(days=400)

    lines = []
    for i, code in enumerate(sorted(codes), 1):
        try:
            bars = jquants.get_daily_bars(code, start, today)
            jquants.throttled_sleep(0.2)
        except Exception as e:
            print(f"  skip {code}: {e}")
            continue

        result = compute_lines(bars)
        if not result:
            print(f"  skip {code}: データ不足")
            continue

        lines.append({
            "code": code,
            "target_price": result["target_price"],
            "stop_loss": result["stop_loss"],
        })
        print(
            f"  [{i}/{len(codes)}] {code}  現在値={result['current']}  "
            f"利確={result['target_price']} ({result['target_pct']:+.1f}%)  "
            f"損切={result['stop_loss']} ({result['stop_pct']:+.1f}%)"
        )

    print(f"\n→ lines シートに {len(lines)}銘柄 書き込み...")
    sheets.replace_all_lines(lines)
    print("✓ 完了")


if __name__ == "__main__":
    main()
