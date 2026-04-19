---
description: TOPIX500からおすすめ銘柄10件を自動推薦（テクニカル + ファンダメンタル + セカンドオピニオン）してGoogleシートに保存
---

# おすすめ銘柄の自動推薦ワークフロー

毎朝このコマンドを叩けば、最新のおすすめ10銘柄がGoogleシートに書き込まれ、Streamlitアプリから確認できるようになる。

以下の手順を**順番に**実行すること。

## Step 1: 候補銘柄の絞り込み

Bashツールで以下を実行:

```
.venv/bin/python scripts/screen_candidates.py
```

完了まで 5〜15分ほどかかる（TOPIX500約500銘柄分のAPIコール）。完了後、`data/candidates.json` が生成されていることを確認。

## Step 2: テクニカル分析 & ファンダメンタル分析 を並列実行

Agent ツールで **2つのエージェントを並列に呼び出す**:

1. `subagent_type: "technical-analyst"` — `data/candidates.json` を読み `data/technical_recommendations.json` を書き出す
2. `subagent_type: "fundamental-analyst"` — 同じ候補から `data/fundamental_recommendations.json` を書き出す

両エージェントにプロンプトとして「data/candidates.json を読み、指示通り上位10銘柄を10段階評価して所定のパスに書き出してください」を渡すだけでよい。

## Step 3: プライマリ推薦を統合

Bashツールで:

```
.venv/bin/python scripts/merge_recommendations.py
```

→ `data/primary_recommendations.json` が生成される（テクニカル+ファンダ合議の最終10銘柄）。

## Step 4: セカンドオピニオン

Agent ツールで `subagent_type: "second-opinion"` を呼び出し。
プロンプト: 「data/primary_recommendations.json, data/technical_recommendations.json, data/fundamental_recommendations.json, data/candidates.json を読み、指示通り各銘柄に批判的レビューを書いて data/second_opinion.json に書き出してください」

## Step 5: Googleシートに保存

Bashツールで:

```
.venv/bin/python scripts/save_to_sheet.py
```

→ Googleシートの `recommendations` タブに10銘柄分の推薦データが書き込まれる。

## Step 6: 保有・監視銘柄の利確/損切ラインを更新

Bashツールで:

```
.venv/bin/python scripts/update_lines.py
```

→ Googleシートの `lines` タブに保有+監視銘柄の最新ラインが書き込まれる（銘柄が無ければスキップ）。

## 完了報告

最後にユーザーに以下を短く報告:

- 推薦された10銘柄のコードと会社名、テクニカル/ファンダの平均スコア
- セカンドオピニオンで `verdict="disagree"` になった銘柄があれば特記
- Streamlit アプリを起動すれば「おすすめ銘柄」タブで確認できることを伝える
