"""Google Sheets接続テスト"""
import os
from pathlib import Path
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
CRED_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file(CRED_PATH, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key(SHEET_ID)
print(f"✓ 接続成功: {sheet.title}")
print(f"  既存ワークシート: {[ws.title for ws in sheet.worksheets()]}")
