"""設定の読み込み

優先順:
  1. Streamlit Cloud の st.secrets (デプロイ環境)
  2. OSの環境変数 / .env ファイル (ローカル開発 / scripts)

認証情報の扱い:
  - `GOOGLE_CREDENTIALS_JSON` (inline JSON文字列 or dict) があればそれを使う
  - 無ければ `GOOGLE_CREDENTIALS_PATH` (ローカルファイルパス) を使う
  - get_google_credentials_info() が dict を返すので sheets.py で統一的に扱える
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()


def _load_streamlit_secrets() -> dict:
    """st.secrets からキーを拾う。失敗は静かに無視（scripts実行時など）"""
    out: dict = {}
    try:
        import streamlit as st  # type: ignore
    except ImportError:
        return out
    # st.secrets にアクセスすると secrets.toml が無ければ例外、個別に try
    for key in ("JQUANTS_API_KEY", "GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_JSON", "GOOGLE_CREDENTIALS_PATH"):
        try:
            v = st.secrets[key]
        except Exception:
            continue
        if v:
            out[key] = v
    return out


_ST_SECRETS = _load_streamlit_secrets()


def _get(key: str, required: bool = True):
    v = _ST_SECRETS.get(key)
    if v is None or v == "":
        v = os.environ.get(key)
    if required and not v:
        raise RuntimeError(
            f"必須の設定 '{key}' が見つかりません。"
            f".env または .streamlit/secrets.toml に設定してください。"
        )
    return v


JQUANTS_API_KEY: str = _get("JQUANTS_API_KEY")
GOOGLE_SHEET_ID: str = _get("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_PATH = _get("GOOGLE_CREDENTIALS_PATH", required=False)
GOOGLE_CREDENTIALS_JSON = _get("GOOGLE_CREDENTIALS_JSON", required=False)


def get_google_credentials_info() -> dict:
    """Google サービスアカウントの認証情報を dict で返す。
    Cloud: secrets.toml の GOOGLE_CREDENTIALS_JSON (TOML dict or JSON str) から
    Local: ファイルパス GOOGLE_CREDENTIALS_PATH から
    """
    if GOOGLE_CREDENTIALS_JSON:
        if isinstance(GOOGLE_CREDENTIALS_JSON, str):
            return json.loads(GOOGLE_CREDENTIALS_JSON)
        # Streamlit Secrets は dict ではなく AttrDict 系なので dict() で展開
        return dict(GOOGLE_CREDENTIALS_JSON)
    if GOOGLE_CREDENTIALS_PATH:
        with open(GOOGLE_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    raise RuntimeError(
        "Google認証情報が未設定: GOOGLE_CREDENTIALS_JSON または GOOGLE_CREDENTIALS_PATH が必要"
    )
