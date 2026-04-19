"""StockCheck - 保有株 & おすすめ銘柄ビューア"""
from datetime import date, timedelta
import streamlit as st
import pandas as pd
from lib import jquants, sheets

st.set_page_config(page_title="StockCheck", page_icon="📈", layout="wide")
st.title("📈 StockCheck")


@st.cache_data(ttl=300)
def _fetch_prices(codes: tuple[str, ...]) -> dict[str, float]:
    out = {}
    for c in codes:
        bar = jquants.get_latest_close(c)
        if bar:
            out[c] = bar["C"]
    return out


@st.cache_data(ttl=3600)
def _fetch_name(code: str) -> str:
    info = jquants.get_company_info(code)
    return info["CoName"] if info else ""


@st.cache_data(ttl=300)
def _load_recommendations() -> list[dict]:
    return sheets.list_recommendations()


@st.cache_data(ttl=300)
def _load_lines() -> dict[str, dict]:
    """lines シートを {code: {target_price, stop_loss, updated_at}} で返す"""
    return {str(r["code"]): r for r in sheets.list_lines()}


@st.cache_data(ttl=3600)
def _fetch_topix_regime() -> dict:
    """TOPIX の現在値・200日移動平均を取得し、相場環境を判定

    2022-01パイロットbacktest結果: TOPIX < MA200 の下落トレンド入り口では
    本戦略(低PER+モメンタム+52w高値接近)が逆機能 → 警告表示で人間判断を介在
    """
    today = date.today()
    start = today - timedelta(days=320)  # 200営業日≒280暦日、余裕持たせて320日
    try:
        data = jquants._get("/indices/bars/daily/topix", {
            "from": start.strftime("%Y%m%d"),
            "to": today.strftime("%Y%m%d"),
        }).get("data", [])
    except Exception:
        return {}
    closes = [b["C"] for b in sorted(data, key=lambda b: b.get("Date", "")) if b.get("C") is not None]
    if len(closes) < 200:
        return {}
    current = closes[-1]
    ma_200 = sum(closes[-200:]) / 200
    ratio = current / ma_200
    return {
        "current": round(current, 2),
        "ma_200": round(ma_200, 2),
        "ratio": round(ratio, 4),
        "deviation_pct": round((ratio - 1) * 100, 2),
    }


@st.dialog("監視銘柄に追加")
def _add_to_watchlist_dialog(code: str, name: str, current_price) -> None:
    st.markdown(f"### {code} {name}")
    try:
        price_value = float(current_price) if current_price not in (None, "") else 0.0
    except (ValueError, TypeError):
        price_value = 0.0
    if price_value:
        st.caption(f"現在値: ¥{price_value:,.0f}")

    existing = [w for w in sheets.list_watchlist() if str(w.get("code")) == str(code)]
    if existing:
        st.warning("⚠ この銘柄はすでに監視リストに登録されています。")
        return

    with st.form(f"add_watch_{code}"):
        note = st.text_input("メモ（任意）", placeholder="例: 決算発表後に検討、〇〇円まで下がったら買う")
        submitted = st.form_submit_button("👁️ 監視に追加", type="primary", use_container_width=True)
        if submitted:
            try:
                sheets.add_watchlist(code, name, note)
                st.success(f"✓ {code} {name} を監視銘柄に追加しました")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"エラー: {e}")


@st.dialog("保有銘柄に追加")
def _add_to_holdings_dialog(code: str, name: str, current_price) -> None:
    st.markdown(f"### {code} {name}")
    try:
        price_value = float(current_price) if current_price not in (None, "") else 0.0
    except (ValueError, TypeError):
        price_value = 0.0
    if price_value:
        st.caption(f"現在値: ¥{price_value:,.0f}")

    # 重複チェック
    existing = [h for h in sheets.list_holdings() if str(h.get("code")) == str(code)]
    if existing:
        st.warning(
            f"⚠ この銘柄はすでに保有登録されています（{existing[0].get('shares')}株）。"
            "追加すると重複します。先に📊保有銘柄タブから削除してから登録してください。"
        )

    with st.form(f"add_from_reco_{code}"):
        shares = st.number_input("株数", min_value=1, step=100, value=100)
        avg_price = st.number_input(
            "平均取得単価（円）",
            min_value=0.0,
            step=1.0,
            value=price_value,
            help="空欄なら現在値が入ります。実際の買値を入れてください。",
        )
        submitted = st.form_submit_button("✓ 追加する", type="primary", use_container_width=True)
        if submitted:
            try:
                sheets.add_holding(code, name, int(shares), float(avg_price))
                st.success(f"✓ {code} {name} を保有銘柄に追加しました")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"エラー: {e}")


tab_hold, tab_watch, tab_reco = st.tabs(["📊 保有銘柄", "👁️ 監視銘柄", "⭐ おすすめ銘柄"])

# ======================================================
# 保有銘柄タブ
# ======================================================
with tab_hold:
    with st.expander("➕ 保有銘柄を追加", expanded=False):
        with st.form("add_holding"):
            col1, col2, col3 = st.columns(3)
            code = col1.text_input("銘柄コード (4桁)", max_chars=4)
            shares = col2.number_input("株数", min_value=1, step=100, value=100)
            avg_price = col3.number_input("平均取得単価 (円)", min_value=0.0, step=1.0, value=0.0)
            submitted = st.form_submit_button("追加")
            if submitted:
                if not code or not code.isdigit() or len(code) != 4:
                    st.error("銘柄コードは4桁の数字で入力してください")
                else:
                    try:
                        name = _fetch_name(code)
                        if not name:
                            st.error(f"銘柄コード {code} の情報が取得できませんでした")
                        else:
                            sheets.add_holding(code, name, int(shares), float(avg_price))
                            st.success(f"✓ {code} {name} を追加しました")
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"エラー: {e}")

    st.subheader("保有銘柄")
    holdings = sheets.list_holdings()

    if not holdings:
        st.info("まだ保有銘柄が登録されていません。上の「保有銘柄を追加」から登録してください。")
    else:
        df = pd.DataFrame(holdings)
        codes = tuple(df["code"].astype(str).tolist())

        with st.spinner("現在値を取得中..."):
            prices = _fetch_prices(codes)

        df["current"] = df["code"].astype(str).map(prices)
        df["market_value"] = df["current"] * df["shares"]
        df["cost"] = df["avg_price"] * df["shares"]
        df["pnl"] = df["market_value"] - df["cost"]
        df["pnl_pct"] = (df["pnl"] / df["cost"]) * 100

        lines_map = _load_lines()
        df["target_price"] = df["code"].astype(str).map(lambda c: lines_map.get(c, {}).get("target_price"))
        df["stop_loss"] = df["code"].astype(str).map(lambda c: lines_map.get(c, {}).get("stop_loss"))

        display = df[["code", "name", "shares", "avg_price", "current", "pnl", "pnl_pct", "target_price", "stop_loss"]].copy()
        display.columns = ["コード", "銘柄名", "株数", "取得単価", "現在値", "含み損益", "損益率(%)", "利確ライン", "損切ライン"]

        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "取得単価": st.column_config.NumberColumn(format="¥%.0f"),
                "現在値": st.column_config.NumberColumn(format="¥%.0f"),
                "含み損益": st.column_config.NumberColumn(format="¥%+.0f"),
                "損益率(%)": st.column_config.NumberColumn(format="%+.2f%%"),
                "利確ライン": st.column_config.NumberColumn(format="¥%.0f"),
                "損切ライン": st.column_config.NumberColumn(format="¥%.0f"),
            },
        )

        # ライン更新日の表示
        any_line = next(iter(lines_map.values()), None)
        if any_line:
            st.caption(f"利確/損切ライン 最終更新: {any_line.get('updated_at', '')}")
        else:
            st.caption("💡 利確/損切ラインはまだ未生成です。PCで `/recommend-stocks` を実行すると更新されます。")

        total_cost = df["cost"].sum()
        total_value = df["market_value"].sum()
        total_pnl = df["pnl"].sum()
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("取得額合計", f"¥{total_cost:,.0f}")
        c2.metric("評価額合計", f"¥{total_value:,.0f}")
        c3.metric("含み損益", f"¥{total_pnl:+,.0f}")
        c4.metric("損益率", f"{total_pnl_pct:+.2f}%")

        with st.expander("🗑️ 銘柄を削除"):
            del_code = st.selectbox(
                "削除する銘柄",
                options=df["code"].astype(str).tolist(),
                format_func=lambda c: f"{c} {df[df['code'].astype(str)==c]['name'].iloc[0]}",
            )
            if st.button("削除する", type="secondary"):
                sheets.delete_holding(del_code)
                st.cache_data.clear()
                st.rerun()


# ======================================================
# 監視銘柄タブ
# ======================================================
with tab_watch:
    with st.expander("➕ 監視銘柄を追加", expanded=False):
        with st.form("add_watch_manual"):
            wcol1, wcol2 = st.columns(2)
            wcode = wcol1.text_input("銘柄コード (4桁)", max_chars=4, key="watch_code")
            wnote = wcol2.text_input("メモ（任意）", key="watch_note")
            wsubmit = st.form_submit_button("追加")
            if wsubmit:
                if not wcode or not wcode.isdigit() or len(wcode) != 4:
                    st.error("銘柄コードは4桁の数字で入力してください")
                else:
                    try:
                        wname = _fetch_name(wcode)
                        if not wname:
                            st.error(f"銘柄コード {wcode} の情報が取得できませんでした")
                        else:
                            sheets.add_watchlist(wcode, wname, wnote)
                            st.success(f"✓ {wcode} {wname} を監視リストに追加しました")
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"エラー: {e}")

    st.subheader("監視中の銘柄")
    watchlist = sheets.list_watchlist()

    if not watchlist:
        st.info(
            "まだ監視銘柄がありません。\n\n"
            "上の「監視銘柄を追加」または「⭐ おすすめ銘柄」タブの「👁️ 監視に追加」ボタンから登録できます。"
        )
    else:
        wdf = pd.DataFrame(watchlist)
        wcodes = tuple(wdf["code"].astype(str).tolist())

        with st.spinner("現在値を取得中..."):
            wprices = _fetch_prices(wcodes)

        wdf["current"] = wdf["code"].astype(str).map(wprices)

        wlines_map = _load_lines()
        wdf["target_price"] = wdf["code"].astype(str).map(lambda c: wlines_map.get(c, {}).get("target_price"))
        wdf["stop_loss"] = wdf["code"].astype(str).map(lambda c: wlines_map.get(c, {}).get("stop_loss"))

        wdisplay = wdf[["code", "name", "current", "target_price", "stop_loss", "note", "added_at"]].copy()
        wdisplay.columns = ["コード", "銘柄名", "現在値", "利確ライン", "損切ライン", "メモ", "追加日"]

        st.dataframe(
            wdisplay,
            hide_index=True,
            use_container_width=True,
            column_config={
                "現在値": st.column_config.NumberColumn(format="¥%.0f"),
                "利確ライン": st.column_config.NumberColumn(format="¥%.0f"),
                "損切ライン": st.column_config.NumberColumn(format="¥%.0f"),
            },
        )

        with st.expander("🗑️ 監視銘柄を削除"):
            wdel_code = st.selectbox(
                "削除する銘柄",
                options=wdf["code"].astype(str).tolist(),
                format_func=lambda c: f"{c} {wdf[wdf['code'].astype(str)==c]['name'].iloc[0]}",
                key="watch_del",
            )
            if st.button("削除する", type="secondary", key="watch_del_btn"):
                sheets.delete_watchlist(wdel_code)
                st.cache_data.clear()
                st.rerun()


# ======================================================
# おすすめ銘柄タブ
# ======================================================
with tab_reco:
    # 市場環境バロメーター (2022-01 バックテストで発見された戦略の弱点を可視化)
    with st.spinner("TOPIX 相場環境を確認中..."):
        regime = _fetch_topix_regime()
    if regime:
        dev = regime["deviation_pct"]
        # 3段階の注意喚起 (閾値は一般的な市場センチメント指標、バックテスト最適化していない)
        if dev >= 0:
            level_emoji = "🟢"
            level_text = "戦略有効な環境"
            level_detail = "TOPIX が 200日移動平均を上回っており、上昇トレンド基調。本戦略(低PER+モメンタム)が機能しやすい局面です。"
            box = st.success
        elif dev >= -3:
            level_emoji = "🟡"
            level_text = "注意が必要な環境"
            level_detail = "TOPIX が 200日移動平均を小幅下回っています。トレンド転換の可能性あり。新規エントリーは慎重に。"
            box = st.warning
        else:
            level_emoji = "🔴"
            level_text = "戦略機能しにくい環境"
            level_detail = (
                "TOPIX が 200日移動平均を明確に下回っています (下落トレンド入り口)。"
                "過去検証 (2022-01) でこのような局面では本戦略は **母集団平均にも負けました** "
                "(低PER銘柄がバリュートラップ化、モメンタムが逆機能)。"
                "**新規エントリーは推奨しません**。"
            )
            box = st.error
        box(f"{level_emoji} **{level_text}**  |  TOPIX {regime['current']} / MA200 {regime['ma_200']} ({dev:+.2f}%)")
        with st.expander("📖 相場環境について"):
            st.markdown(level_detail)
            st.caption(
                "※ 判定は単純な TOPIX vs 200日移動平均の位置関係。"
                "戦略パラメータの最適化結果ではなく、一般的な市場センチメント指標として表示しています。"
            )

    recos = _load_recommendations()

    if not recos:
        st.info(
            "まだおすすめ銘柄が生成されていません。\n\n"
            "PCで Claude Code を開いて `/recommend-stocks` を実行すると、"
            "当日のおすすめ10銘柄が自動生成されます。"
        )
    else:
        generated = recos[0].get("generated_at", "")
        st.caption(f"最終更新: {generated}")

        for r in recos:
            with st.container(border=True):
                head_l, head_r = st.columns([3, 1])
                with head_l:
                    st.markdown(f"### {r.get('code')} {r.get('name')}")
                    st.caption(f"{r.get('sector', '')} ・ 現在値 ¥{r.get('current_price', '')}")
                with head_r:
                    verdict = r.get("verdict", "")
                    badge = {
                        "agree": ":green[✓ 同意]",
                        "caution": ":orange[⚠ 注意]",
                        "disagree": ":red[✗ 反対]",
                    }.get(verdict, "")
                    if badge:
                        st.markdown(badge)

                # スコア
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("テクニカル", f"{r.get('technical_score', '')}/10")
                s2.metric("ファンダ", f"{r.get('fundamental_score', '')}/10")
                s3.metric("利確目安", f"¥{r.get('target_price', '')}")
                s4.metric("損切り目安", f"¥{r.get('stop_loss', '')}")

                # 推薦理由
                tech_reason = r.get("technical_reason", "")
                fund_reason = r.get("fundamental_reason", "")
                if tech_reason:
                    st.markdown(f"**📈 テクニカル:** {tech_reason}")
                if fund_reason:
                    st.markdown(f"**📊 ファンダ:** {fund_reason}")

                fair = r.get("fair_value")
                if fair:
                    st.caption(f"適正株価見立て: ¥{fair}（割高リスク: {r.get('valuation_risk', '')}）")

                # 保有 / 監視追加ボタン（2列）
                btn_hold_col, btn_watch_col = st.columns(2)
                if btn_hold_col.button(
                    "➕ 保有に追加",
                    key=f"add_hold_reco_{r.get('code')}",
                    use_container_width=True,
                ):
                    _add_to_holdings_dialog(
                        str(r.get("code")),
                        str(r.get("name")),
                        r.get("current_price"),
                    )
                if btn_watch_col.button(
                    "👁️ 監視に追加",
                    key=f"add_watch_reco_{r.get('code')}",
                    use_container_width=True,
                ):
                    _add_to_watchlist_dialog(
                        str(r.get("code")),
                        str(r.get("name")),
                        r.get("current_price"),
                    )

                # セカンドオピニオン
                contrarian = r.get("contrarian_view", "")
                if contrarian:
                    with st.expander("🔍 セカンドオピニオン"):
                        level = r.get("second_opinion_level", "")
                        st.caption(f"懸念度: **{level}**")
                        st.write(contrarian)
                        bs = r.get("blind_spots", "")
                        if bs:
                            st.caption(f"見落とし候補: {bs}")
