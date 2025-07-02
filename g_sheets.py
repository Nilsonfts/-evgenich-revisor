# g_sheets.py
import gspread
import json
import logging
from typing import Optional
from config import GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON

# --- Функции для работы с Google Sheets ---
def get_sheet() -> Optional[gspread.Worksheet]:
    if not all([gspread, GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON]):
        logging.error("gspread не импортирован или переменные для Google не заданы.")
        return None
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        return gc.open_by_key(GOOGLE_SHEET_KEY).sheet1
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

# ... (сюда можно перенести и другие функции для работы с таблицами,
# например, create_sheet_header_if_needed и append_shift_to_google_sheet)
