# g_sheets.py
import json
import logging
import datetime
import pytz
from typing import Optional
from collections import Counter

# Используем gspread, если он установлен
try:
    import gspread
except ImportError:
    gspread = None

# Импортируем переменные и функции из наших модулей
from config import GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON, EXPECTED_VOICES_PER_SHIFT
from state import chat_configs
from utils import get_chat_title

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
        # Проверяем значение в первой ячейке, чтобы определить, нужна ли шапка
        if worksheet.acell('A1').value is None:
            headers = [
                "Дата", "ID Чата", "Название Чата", "Бренд", "Город",
                "ID Ведущего", "Тег Ведущего", "Голосовых (шт)", "План (шт)",
                "Выполнение (%)", "Перерывов (шт)", "Опозданий (шт)",
                "Средний ритм (мин)", "Макс. пауза (мин)", "Ср. длина ГС (сек)",
                "Рекомендация", "Затронутые темы"
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            # Форматируем шапку жирным и центрируем
            worksheet.format('A1:R1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
            logging.info("Создана шапка в Google Таблице.")
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(bot, chat_id: int, data: dict, analytical_conclusion: str):
    """Добавляет строку с отчетом о смене в Google Таблицу."""
    worksheet = get_sheet()
    if not worksheet:
        logging.error(f"Выгрузка в Google Sheets для чата {chat_id} невозможна: лист не найден.")
        return
        
    create_sheet_header_if_needed(worksheet)

    main_id = data.get('main_id')
    user_data = data.get('users', {}).get(main_id)
    if not user_data:
        logging.warning(f"Нет данных по ведущему для выгрузки в чате {chat_id}.")
        return

    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0

    avg_delta = sum(user_data.get('voice_deltas', [])) / len(user_data['voice_deltas']) if user_data.get('voice_deltas') else 0
    max_pause = max(user_data.get('voice_deltas', [0]))
    avg_duration = sum(user_data.get('voice_durations', [])) / len(user_data['voice_durations']) if user_data.get('voice_durations') else 0

    chat_config = chat_configs.get(chat_id, {})
    brand = chat_config.get('brand', 'N/A')
    city = chat_config.get('city', 'N/A')

    ad_counts = Counter(user_data.get('recognized_ads', []))
    recognized_ads_str = ", ".join([f"{ad} (x{count})" for ad, count in ad_counts.items()]) or "Нет данных"

    row_data = [
        data.get('shift_start', now_moscow).strftime('%d.%m.%Y'),
        chat_id,
        get_chat_title(bot, chat_id),  # Передаем bot в get_chat_title
        brand,
        city,
        main_id,
        user_data.get('username', 'N/A'),
        user_data.get('count', 0),
        shift_goal,
        f"{plan_percent:.0f}%",
        user_data.get('breaks_count', 0),
        user_data.get('late_returns', 0),
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
