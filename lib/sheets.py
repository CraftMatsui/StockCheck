"""Google Sheets 永続化レイヤー"""
from datetime import date
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials
from .config import GOOGLE_SHEET_ID, get_google_credentials_info

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HOLDINGS_HEADERS = ["code", "name", "shares", "avg_price", "added_at"]
HOLDINGS_SHEET = "holdings"

WATCHLIST_HEADERS = ["code", "name", "note", "added_at"]
WATCHLIST_SHEET = "watchlist"

LINES_HEADERS = ["code", "target_price", "stop_loss", "updated_at"]
LINES_SHEET = "lines"

RECOMMENDATIONS_SHEET = "recommendations"


def _open_book() -> gspread.Spreadsheet:
    info = get_google_credentials_info()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID)


def _ensure_worksheet(book: gspread.Spreadsheet, title: str, headers: list[str]) -> gspread.Worksheet:
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=title, rows=100, cols=len(headers))
        ws.append_row(headers)
        return ws
    # ヘッダが無い場合は追加
    first_row = ws.row_values(1)
    if first_row != headers:
        ws.clear()
        ws.append_row(headers)
    return ws


def get_holdings_ws() -> gspread.Worksheet:
    return _ensure_worksheet(_open_book(), HOLDINGS_SHEET, HOLDINGS_HEADERS)


def list_holdings() -> list[dict]:
    ws = get_holdings_ws()
    return ws.get_all_records()


def add_holding(code: str, name: str, shares: int, avg_price: float) -> None:
    ws = get_holdings_ws()
    ws.append_row([
        code,
        name,
        shares,
        avg_price,
        date.today().isoformat(),
    ])


def delete_holding(code: str) -> bool:
    ws = get_holdings_ws()
    rows = ws.get_all_records()
    for i, row in enumerate(rows, start=2):  # 1-indexed, skip header
        if str(row.get("code")) == str(code):
            ws.delete_rows(i)
            return True
    return False


def list_recommendations() -> list[dict]:
    """recommendations タブの中身を返す。未生成なら空リスト。"""
    book = _open_book()
    try:
        ws = book.worksheet(RECOMMENDATIONS_SHEET)
    except gspread.WorksheetNotFound:
        return []
    return ws.get_all_records()


def get_watchlist_ws() -> gspread.Worksheet:
    return _ensure_worksheet(_open_book(), WATCHLIST_SHEET, WATCHLIST_HEADERS)


def list_watchlist() -> list[dict]:
    ws = get_watchlist_ws()
    return ws.get_all_records()


def add_watchlist(code: str, name: str, note: str = "") -> None:
    ws = get_watchlist_ws()
    ws.append_row([code, name, note, date.today().isoformat()])


def delete_watchlist(code: str) -> bool:
    ws = get_watchlist_ws()
    rows = ws.get_all_records()
    for i, row in enumerate(rows, start=2):
        if str(row.get("code")) == str(code):
            ws.delete_rows(i)
            return True
    return False


def get_lines_ws() -> gspread.Worksheet:
    return _ensure_worksheet(_open_book(), LINES_SHEET, LINES_HEADERS)


def list_lines() -> list[dict]:
    ws = get_lines_ws()
    return ws.get_all_records()


def replace_all_lines(lines: list[dict]) -> None:
    """lines シートを丸ごと上書き。各要素は code/target_price/stop_loss を含む dict"""
    ws = get_lines_ws()
    ws.clear()
    ws.append_row(LINES_HEADERS)
    today = date.today().isoformat()
    rows = [
        [
            str(ln.get("code", "")),
            ln.get("target_price", ""),
            ln.get("stop_loss", ""),
            today,
        ]
        for ln in lines
    ]
    if rows:
        ws.append_rows(rows)
