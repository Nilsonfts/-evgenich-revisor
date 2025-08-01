# g_sheets.py
import json
import logging
import datetime
import pytz
from typing import Optional
from collections import Counter

try:
    import gspread
except ImportError:
    gspread = None

from config import GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON
from state import chat_configs
from utils import get_chat_title
from models import ShiftData # Импортируем нашу модель

def get_sheet() -> Optional[gspread.Worksheet]:
    """Подключается к Google Sheets и возвращает рабочий лист."""
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

def create_sheet_header_if_needed(worksheet: gspread.Worksheet):
    """Создает шапку в таблице, если она пустая."""
    try:
        if worksheet.acell('A1').value is None:
            headers = [
                "Дата", "ID Чата", "Название Чата", "Бренд", "Город",
                "ID Ведущего", "Тег Ведущего", "Голосовых (шт)", "План (шт)",
                "Выполнение (%)", "Перерывов (шт)", "Опозданий (шт)",
                "Средний ритм (мин)", "Макс. пауза (мин)", "Ср. длина ГС (сек)",
                "Рекомендация", "Затронутые темы"
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:R1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
            logging.info("Создана шапка в Google Таблице.")
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(bot, chat_id: int, data: ShiftData, analytical_conclusion: str):
    """Добавляет строку с отчетом о смене в Google Таблицу."""
    worksheet = get_sheet()
    if not worksheet:
        logging.error(f"Выгрузка в Google Sheets для чата {chat_id} невозможна: лист не найден.")
        return
        
    create_sheet_header_if_needed(worksheet)

    main_id = data.main_id
    user_data = data.users.get(main_id)
    if not user_data:
        logging.warning(f"Нет данных по ведущему для выгрузки в чате {chat_id}.")
        return

    shift_goal = data.shift_goal
    plan_percent = (user_data.count / shift_goal * 100) if shift_goal > 0 else 0
    avg_delta = sum(user_data.voice_deltas) / len(user_data.voice_deltas) if user_data.voice_deltas else 0
    max_pause = max(user_data.voice_deltas or [0])
    avg_duration = sum(user_data.voice_durations) / len(user_data.voice_durations) if user_data.voice_durations else 0

    chat_config = chat_configs.get(str(chat_id), {})
    brand = chat_config.get('brand', 'N/A')
    city = chat_config.get('city', 'N/A')

    ad_counts = Counter(user_data.recognized_ads)
    recognized_ads_str = ", ".join([f"{ad} (x{count})" for ad, count in ad_counts.items()]) or "Нет данных"

    start_date = datetime.datetime.fromisoformat(data.shift_start_time).strftime('%d.%m.%Y')
        
    row_data = [
        start_date,
        str(chat_id),
        get_chat_title(bot, chat_id),
        brand,
        city,
        str(main_id),
        user_data.username,
        user_data.count,
        shift_goal,
        f"{plan_percent:.0f}%",
        user_data.breaks_count,
        user_data.late_returns,
        f"{avg_delta:.1f}",
        f"{max_pause:.1f}",
        f"{avg_duration:.1f}",
        analytical_conclusion,
        recognized_ads_str
    ]
    try:
        worksheet.append_row(row_data, value_input_option='USER_ENTERED')
        logging.info(f"Данные по смене в чате {chat_id} успешно добавлены в Google Таблицу.")
    except Exception as e:
        logging.error(f"Не удалось добавить данные в Google Таблицу для чата {chat_id}: {e}")
