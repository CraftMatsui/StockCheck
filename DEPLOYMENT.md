# Streamlit Cloud デプロイ手順

このアプリを https://share.streamlit.io にデプロイして、スマホから外出先でもアクセスできるようにする手順。

## 1. 事前確認
- GitHub アカウント（無料OK）
- J-Quants API キー（`.env` にあるもの）
- Google サービスアカウント JSON（`credentials/service_account.json`）
- Google Sheet ID（`.env` の `GOOGLE_SHEET_ID`）

## 2. GitHub にプッシュ

### 2-1. 初めての git init の場合
```bash
cd /Users/craft/Projects/StockCheck
git init
git add .
git commit -m "Initial commit"
```

### 2-2. GitHub にリポジトリを作る
GitHub の Web で `StockCheck` リポジトリを新規作成（**private 推奨**、public でも可）。その後:

```bash
git remote add origin https://github.com/<あなたのユーザー名>/StockCheck.git
git branch -M main
git push -u origin main
```

### 2-3. `.gitignore` の動作確認（超重要）
push 前に **秘密情報が含まれていないこと** を確認:
```bash
git ls-files | grep -E "(\.env|service_account|secrets\.toml$)"
```
**何も出力されなければOK**。出たら即 push 中止、対象ファイルを `.gitignore` に追加してから `git rm --cached <file>` して再 commit。

## 3. Streamlit Community Cloud に接続

### 3-1. サインアップ
https://share.streamlit.io → "Sign up" → GitHub アカウントで連携

### 3-2. 新規アプリを作成
- "New app" → "From existing repo" を選ぶ
- Repository: `<ユーザー名>/StockCheck`
- Branch: `main`
- Main file path: `app.py`
- App URL: 好きなサブドメインを指定（例: `craft-stockcheck` → `https://craft-stockcheck.streamlit.app`）

### 3-3. Secrets を登録
"Advanced settings" → "Secrets" に以下を貼り付け（`secrets.toml` の書式）:

```toml
JQUANTS_API_KEY = "実際のAPIキー"
GOOGLE_SHEET_ID = "実際のシートID"

[GOOGLE_CREDENTIALS_JSON]
type = "service_account"
project_id = "xxx"
private_key_id = "xxx"
private_key = """-----BEGIN PRIVATE KEY-----
<改行も含めて service_account.json の値をそのまま>
-----END PRIVATE KEY-----
"""
client_email = "xxx@xxx.iam.gserviceaccount.com"
client_id = "xxx"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
universe_domain = "googleapis.com"
```

参考: `.streamlit/secrets.toml.example` にテンプレあり。

### 3-4. デプロイ
"Deploy!" ボタン → 数分待つとビルド完了 → URL にアクセスして動作確認。

## 4. スマホから登録

1. デプロイ完了した URL をスマホのブラウザで開く
2. ホーム画面に追加（iPhone: Safari の共有 → "ホーム画面に追加"、Android: Chrome メニュー → "ホーム画面に追加"）
3. 以降はアプリアイコンから1タップで起動

## 5. 再デプロイ

GitHub の main ブランチに push すると **自動で再デプロイされる**。

```bash
git add -A
git commit -m "変更内容"
git push
```

## トラブルシューティング

### `StreamlitSecretNotFoundError` が出る
→ Cloud 側の Secrets 登録漏れ。secrets.toml.example を参考に再設定。

### `RuntimeError: 必須の設定 'GOOGLE_CREDENTIALS_JSON' が見つかりません`
→ TOML の `[GOOGLE_CREDENTIALS_JSON]` セクションの書式誤り。特に `private_key` の改行とトリプルクォートに注意。

### `SpreadsheetNotFound` が出る
→ サービスアカウントのメールアドレスに Google Sheet を共有していない。Sheet の "共有" から追加。

### 推薦銘柄が更新されない
→ `/recommend-stocks` は手元の PC からしか実行できない（Claude Code が必要）。PC で実行 → 結果が自動で Sheet に保存 → Cloud 側のアプリで反映される流れ。
