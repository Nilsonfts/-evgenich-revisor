# -*- coding: utf-8 -*-
"""
Каноничная финальная версия v9.0:
- Восстановлены и адаптированы под Google Sheets команды /сводка и /analyze.
- Добавлена гибкая конфигурация чатов (часовые пояса, время смены).
- Аналитика генерирует прямые управленческие рекомендации.
- Исправлена работа планировщика для динамического завершения смен.
- Все функции и команды финализированы.
"""

import logging
import os
import json
import datetime
import time
import random
import pytz
import schedule
import threading
import telebot
from telebot import types
from functools import wraps
from typing import Dict, List

# Попытка импорта библиотек для работы с Google Sheets и анализа данных
try:
    import gspread
    import pandas as pd
except ImportError:
    logging.error("Необходимые библиотеки не найдены. Установите их: pip install gspread google-auth-oauthlib pandas")
    gspread = None
    pd = None

# Импорт кастомных фраз
try:
    from phrases import soviet_phrases, BREAK_KEYWORDS, RETURN_CONFIRM_WORDS
except ImportError:
    logging.warning("Файл 'phrases.py' не найден. Используются значения по умолчанию.")
    BREAK_KEYWORDS = ["перерыв", "отдых", "обед", "покурить", "отойду"]
    RETURN_CONFIRM_WORDS = ["вернулся", "на месте", "пришел", "тут"]
    soviet_phrases = {
        "too_short": ["Слишком коротко!"],
        "accept": ["Принято."],
        "return_demand": ["Пора возвращаться к работе."],
        "voice_reminder": ["Вы давно не выходили в эфир."]
    }

# ========================================
#   НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

# ID администраторов и чата для отчетов
BOSS_ID = 196614680  # ID главного руководителя
ADMIN_REPORT_CHAT_ID = -1002645821302 # ID чата, куда дублируются все отчеты

# Ключ Google Таблицы из переменных окружения
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
CHAT_CONFIG_FILE = 'chat_configs.json'

# Параметры смены (могут быть переопределены в конфиге чата)
EXPECTED_VOICES_PER_SHIFT = 80
VOICE_TIMEOUT_MINUTES = 40
VOICE_MIN_DURATION_SECONDS = 3
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60

# Карта часовых поясов
TIMEZONE_MAP = {
    "-1": "Europe/Kaliningrad", "0": "Europe/Moscow", "+1": "Europe/Samara",
    "+2": "Asia/Yekaterinburg", "+3": "Asia/Omsk", "+4": "Asia/Krasnoyarsk",
    "+5": "Asia/Irkutsk", "+6": "Asia/Yakutsk", "+7": "Asia/Vladivostok",
    "+8": "Asia/Magadan", "+9": "Asia/Kamchatka"
}

# Инициализация бота и глобальных переменных
bot = telebot.TeleBot(BOT_TOKEN, threaded=False, parse_mode="Markdown")
chat_data: Dict[int, dict] = {}
user_history: Dict[int, List[str]] = {}
chat_configs: Dict[int, dict] = {}

# ========================================
#   УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ ЧАТОВ
# ========================================
def load_chat_configs():
    global chat_configs
    if not os.path.exists(CHAT_CONFIG_FILE):
        chat_configs = {}
        return
    try:
        with open(CHAT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            chat_configs = {int(k): v for k, v in json.load(f).items()}
            logging.info("Конфигурации чатов успешно загружены.")
    except Exception as e:
        logging.error(f"Ошибка загрузки конфигурации чатов: {e}")
        chat_configs = {}

def save_chat_configs():
    try:
        with open(CHAT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_configs, f, indent=4)
    except IOError as e:
        logging.error(f"Ошибка сохранения конфигурации чатов: {e}")

# ========================================
#   РАБОТА С GOOGLE SHEETS
# ========================================
def get_sheet():
    """Авторизуется и возвращает рабочий лист Google Таблицы."""
    if not gspread or not GOOGLE_SHEET_KEY:
        logging.error("gspread не импортирован или GOOGLE_SHEET_KEY не задан.")
        return None
    try:
        creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_str:
            logging.error("Переменная окружения GOOGLE_CREDENTIALS_JSON не найдена!")
            return None
        
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_KEY)
        return spreadsheet.sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error("Таблица с ключом не найдена. Проверьте ID и права доступа для сервисного аккаунта.")
        return None
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

def create_sheet_header_if_needed(worksheet):
    """Создает шапку в таблице, если она пустая."""
    try:
        if worksheet.acell('A1').value is None:
            headers = [
                "Дата", "ID Чата", "Название Чата", "ID Ведущего", "Тег Ведущего",
                "Голосовых (шт)", "План (шт)", "Выполнение (%)", "Перерывов (шт)",
                "Опозданий (шт)", "Средний ритм (мин)", "Макс. пауза (мин)", "Ср. длина ГС (сек)",
                "Рекомендация"
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:N1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
            logging.info("Создана шапка в Google Таблице.")
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(chat_id, data, analytical_conclusion):
    """Добавляет строку с итогами смены и аналитикой в Google Таблицу."""
    worksheet = get_sheet()
    if not worksheet:
        logging.error("Выгрузка в Google Sheets невозможна: лист не найден.")
        return

    create_sheet_header_if_needed(worksheet)

    main_id = data.get('main_id')
    user_data = data.get('users', {}).get(main_id)
    if not user_data: return

    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    plan_percent = (user_data['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    avg_delta = sum(user_data['voice_deltas']) / len(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    max_pause = max(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    avg_duration = sum(user_data['voice_durations']) / len(user_data['voice_durations']) if user_data['voice_durations'] else 0

    row_data = [
        data.get('shift_start', now).strftime('%d.%m.%Y'),
        chat_id,
        get_chat_title(chat_id),
        main_id,
        user_data['username'],
        user_data['count'],
        EXPECTED_VOICES_PER_SHIFT,
        f"{plan_percent:.0f}%",
        user_data['breaks_count'],
        user_data['late_returns'],
        f"{avg_delta:.1f}",
        f"{max_pause:.1f}",
        f"{avg_duration:.1f}",
        analytical_conclusion
    ]

    try:
        worksheet.append_row(row_data, value_input_option='USER_ENTERED')
        logging.info(f"Данные по смене в чате {chat_id} успешно добавлены в Google Таблицу.")
    except Exception as e:
        logging.error(f"Не удалось добавить данные в Google Таблицу: {e}")

# ========================================
#   ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================
def is_admin(user_id, chat_id):
    """Проверяет, является ли пользователь админом чата."""
    if user_id == BOSS_ID: return True
    if chat_id > 0: return False
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    except Exception:
        return False

def admin_required(func):
    @wraps(func)
    def wrapper(message):
        if not is_admin(message.from_user.id, message.chat.id):
            return bot.reply_to(message, "Эта команда доступна только администраторам чата.")
        return func(message)
    return wrapper

def get_username(user) -> str:
    return f"@{user.username}" if user.username else user.first_name

def init_user_data(user_id, username):
    return {
        'username': username, 'count': 0, 'on_break': False, 'breaks_count': 0, 
        'late_returns': 0, 'last_voice_time': None, 'last_break_time': None, 
        'reminder_sent_at': None, 'response_times': [], 'voice_deltas': [], 
        'voice_durations': [], 'break_start_time': None
    }

def handle_user_return(chat_id, user_id):
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if not user or not user.get('on_break'): return

    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    break_duration_minutes = (now - user['break_start_time']).total_seconds() / 60

    user['on_break'] = False
    
    if break_duration_minutes > BREAK_DURATION_MINUTES:
        user['late_returns'] += 1
        bot.send_message(chat_id, f"✅ {user['username']}, с возвращением! Вы опоздали на {int(break_duration_minutes - BREAK_DURATION_MINUTES)} мин.")
    else:
        bot.send_message(chat_id, f"👍 {user['username']}, с возвращением! Молодец, что вернулись вовремя.")

def get_chat_title(chat_id: int) -> str:
    try:
        return bot.get_chat(chat_id).title or str(chat_id)
    except:
        return str(chat_id)

def save_history_event(chat_id, user_id, username, event_description):
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

# ========================================
#   ОСНОВНЫЕ КОМАНДЫ БОТА
# ========================================
@bot.message_handler(commands=['start', 'старт'])
def handle_start(message):
    chat_id = message.chat.id
    if chat_id > 0:
        return bot.reply_to(message, "Эта команда работает только в групповом чате.")

    from_user = message.from_user
    username = get_username(from_user)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': datetime.datetime.now(pytz.timezone('Europe/Moscow'))}

    if from_user.id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][from_user.id] = init_user_data(from_user.id, username)
    
    if chat_data[chat_id].get('main_id') is not None:
        main_username = chat_data[chat_id].get('main_username', 'Неизвестно')
        return bot.reply_to(message, f"Смена уже занята. Текущий главный: {main_username}.")

    chat_data[chat_id]['main_id'] = from_user.id
    chat_data[chat_id]['main_username'] = username
    bot.send_message(chat_id, f"👑 {username}, вы заступили на смену! Удачи!")
    save_history_event(chat_id, from_user.id, username, "Стал главным на смене")

@bot.message_handler(commands=['restart', 'рестарт'])
@admin_required
def handle_restart(message):
    chat_id = message.chat.id
    if chat_id in chat_data and chat_data[chat_id].get('main_id') is not None:
        chat_data[chat_id]['main_id'] = None
        chat_data[chat_id]['main_username'] = None
        bot.reply_to(message, "🔄 Смена перезапущена. Текущий главный сброшен.")
        save_history_event(chat_id, message.from_user.id, get_username(message.from_user), "Перезапустил смену")
    else:
        bot.reply_to(message, "Активной смены в этом чате и так не было.")

@bot.message_handler(commands=['check', 'промежуточный'])
def check_shift(message):
    chat_id = message.chat.id
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        return bot.reply_to(message, "Смена еще не началась.")
        
    user = data.get('users', {}).get(data['main_id'])
    if not user:
        return bot.reply_to(message, "Не найдены данные по текущему ведущему.")

    plan_percent = (user['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    report_text = (
        f"📋 #Промежуточный_отчет ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})\n"
        f"🎤 Ведущий: {user['username']}\n"
        f"🗣️ Голосовых: {user['count']} из {EXPECTED_VOICES_PER_SHIFT} ({plan_percent:.0f}%)\n"
        f"☕ Перерывов: {user['breaks_count']}\n"
        f"⏳ Задержек после перерыва: {user['late_returns']}"
    )
    bot.reply_to(message, report_text)
    
@bot.message_handler(commands=['отчет'])
@admin_required
def admin_get_final_report(message):
    chat_id = message.chat.id
    send_end_of_shift_report_for_chat(chat_id)

@bot.message_handler(commands=['сводка'])
def my_total_stats(message):
    """Анализирует Google Таблицу и показывает личную сводку."""
    if not pd: return bot.reply_to(message, "Модуль для анализа данных (pandas) не загружен.")
    
    user_id = message.from_user.id
    username = get_username(message.from_user)
    bot.reply_to(message, f"📊 Собираю вашу общую статистику из Google Таблицы, {username}. Минутку...")

    worksheet = get_sheet()
    if not worksheet:
        return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице для получения статистики.")
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty or 'ID Ведущего' not in df.columns:
            return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")
            
        df['ID Ведущего'] = pd.to_numeric(df['ID Ведущего'])
        user_df = df[df['ID Ведущего'] == user_id]

        if user_df.empty:
            return bot.send_message(message.chat.id, f"{username}, не найдено ваших смен в общей статистике.")

        total_shifts = len(user_df)
        total_voices = pd.to_numeric(user_df['Голосовых (шт)']).sum()
        total_breaks = pd.to_numeric(user_df['Перерывов (шт)']).sum()
        total_lates = pd.to_numeric(user_df['Опозданий (шт)']).sum()

        report_text = (
            f"⭐️ **Общая статистика для {username}** ⭐️\n\n"
            f"👑 **Всего смен отработано:** {total_shifts}\n"
            f"🗣️ **Всего голосовых записано:** {total_voices}\n"
            f"☕️ **Всего перерывов:** {total_breaks}\n"
            f"⏳ **Всего опозданий с перерыва:** {total_lates}"
        )
        bot.send_message(message.chat.id, report_text)
    except Exception as e:
        logging.error(f"Ошибка анализа Google Sheets для /сводка: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при анализе данных из таблицы.")

@bot.message_handler(commands=['analyze', 'весьотчет'])
@admin_required
def admin_analyze_all_users(message):
    """Анализирует Google Таблицу и показывает общий рейтинг."""
    if not pd: return bot.reply_to(message, "Модуль для анализа данных (pandas) не загружен.")
    
    bot.reply_to(message, "📊 Анализирую общую статистику из Google Таблицы. Это может занять время...")
    worksheet = get_sheet()
    if not worksheet:
        return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице для анализа.")
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty or 'ID Ведущего' not in df.columns:
            return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")

        # Преобразование типов для корректных вычислений
        numeric_cols = ['Голосовых (шт)', 'Опозданий (шт)']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=numeric_cols, inplace=True)

        summary = df.groupby('Тег Ведущего').agg(
            total_shifts=('Дата', 'count'),
            total_voices=('Голосовых (шт)', 'sum'),
            total_lates=('Опозданий (шт)', 'sum')
        ).reset_index()

        summary['avg_voices'] = summary['total_voices'] / summary['total_shifts']
        summary['lateness_percent'] = (summary['total_lates'] / summary['total_shifts']) * 100
        summary = summary.sort_values(by='avg_voices', ascending=False)

        report_lines = ["📊 **Общая сводка по всем сотрудникам**", "_(На основе данных из Google Sheets)_\n"]
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}

        for i, row in summary.iterrows():
            rank_icon = medals.get(i, f"{i+1}.")
            report_lines.append(
                f"*{rank_icon}* {row['Тег Ведущего']} — *Ср. ГС:* `{row['avg_voices']:.1f}` | *Опоздания:* `{row['lateness_percent']:.0f}%` | *Смен:* `{row['total_shifts']}`"
            )
        
        bot.send_message(message.chat.id, "\n".join(report_lines))
    except Exception as e:
        logging.error(f"Ошибка анализа Google Sheets для /analyze: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при анализе данных из таблицы.")

@bot.message_handler(commands=['выгрузка'])
@admin_required
def admin_export_history(message):
    chat_id = message.chat.id
    history = user_history.get(chat_id)

    if not history:
        return bot.reply_to(message, "История событий для текущей смены пуста.")
        
    try:
        filename = f"history_{chat_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"История событий для чата: {get_chat_title(chat_id)}\n" + "="*40 + "\n" + "\n".join(history))
        
        with open(filename, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="Лог событий текущей смены.")
        
        os.remove(filename)
    except Exception as e:
        logging.error(f"Ошибка при выгрузке истории: {e}")
        bot.reply_to(message, "Произошла ошибка при создании файла истории.")

# ========================================
#   КОМАНДЫ АДМИНИСТРИРОВАНИЯ ЧАТА
# ========================================
@bot.message_handler(commands=['set_timezone'])
@admin_required
def set_timezone(message):
    chat_id = message.chat.id
    try:
        offset = message.text.split()[1]
        tz_name = TIMEZONE_MAP.get(offset)
        if not tz_name:
            return bot.reply_to(message, f"❌ Неверный формат смещения. Укажите смещение от МСК, например: `0`, `+1`, `-2`.")
        
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id]['timezone'] = tz_name
        save_chat_configs()
        local_time = datetime.datetime.now(pytz.timezone(tz_name)).strftime('%H:%M:%S')
        bot.reply_to(message, f"✅ Часовой пояс для этого чата установлен на *{tz_name}* (МСК{offset}).\nТекущее время: *{local_time}*.")
    except IndexError:
        bot.reply_to(message, "Пример использования:\n`/set_timezone +3`")

@bot.message_handler(commands=['тайминг'])
@admin_required
def set_shift_timing(message):
    chat_id = message.chat.id
    try:
        parts = message.text.split()
        start_time_str = parts[1]
        end_time_str = parts[2]
        # Проверка формата времени
        datetime.datetime.strptime(start_time_str, '%H:%M')
        datetime.datetime.strptime(end_time_str, '%H:%M')
        
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id]['start_time'] = start_time_str
        chat_configs[chat_id]['end_time'] = end_time_str
        save_chat_configs()
        bot.reply_to(message, f"✅ График смены для этого чата установлен: с *{start_time_str}* до *{end_time_str}*.")
    except (IndexError, ValueError):
        bot.reply_to(message, "Неверный формат. Пример:\n`/тайминг 19:00 04:00`")

@bot.message_handler(commands=['testsheet'])
@admin_required
def test_google_sheet(message):
    """Тестирует соединение с Google Sheets."""
    bot.reply_to(message, "⚙️ Запускаю тест соединения с Google Sheets...")
    
    worksheet = get_sheet() 
    
    if worksheet:
        try:
            sheet_title = worksheet.spreadsheet.title
            bot.send_message(message.chat.id, 
                f"✅ *УСПЕХ!*\n\n"
                f"Соединение с Google Sheets установлено.\n"
                f"Бот успешно получил доступ к таблице: *'{sheet_title}'*.\n\n"
                f"Выгрузка данных должна работать корректно."
            )
        except Exception as e:
            bot.send_message(message.chat.id, 
                f"❗️*ОШИБКА НА ЭТАПЕ ЧТЕНИЯ!*\n\n"
                f"Подключение установлено, но не удалось прочитать данные. "
                f"Возможно, у сервисного аккаунта недостаточно прав.\n\n"
                f"Детали: `{e}`"
            )
    else:
        bot.send_message(message.chat.id, 
            f"❌ *ПРОВАЛ!*\n\n"
            f"Не удалось подключиться к Google Sheets. Проверьте лог бота в консоли.\n\n"
            f"**Частые причины:**\n"
            f"1. Неверный ID таблицы в `GOOGLE_SHEET_KEY`.\n"
            f"2. Ошибка в данных ключа `GOOGLE_CREDENTIALS_JSON`.\n"
            f"3. Вы не предоставили доступ сервисному аккаунту к вашей таблице (права 'Редактора')."
        )

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = """
*Справка по командам бота:*

`/start` — Назначить себя главным на смене.
`/restart` — Перезапустить смену, сбросив главного.
`/check` или `/промежуточный` — Показать промежуточный отчет.
`/отчет` — (Админ) Сформировать финальный отчет досрочно.
`/выгрузка` — (Админ) Выгрузить историю событий смены.

`/сводка` — Посмотреть свою личную статистику за все время.
`/analyze` — (Админ) Показать рейтинг всех сотрудников.

`/перерыв` или `/обед` — Уйти на перерыв.

*Команды администратора чата:*
`/set_timezone +N` — Установить часовой пояс (например, `+3`).
`/тайминг 19:00 04:00` — Установить время начала и окончания смены.
`/testsheet` - Проверить соединение с Google Sheets.
"""
    bot.reply_to(message, help_text)

# ========================================
#   ОБРАБОТЧИКИ СООБЩЕНИЙ И ДЕЙСТВИЙ
# ========================================
@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
    if chat_id > 0: return

    user_id = message.from_user.id
    username = get_username(message.from_user)
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': now}

    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)

    # Если главный не назначен, первый, кто записал ГС, становится им
    if chat_data[chat_id].get('main_id') is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")
        save_history_event(chat_id, user_id, username, "Стал главным (первое ГС)")

    # Статистику собираем только для главного
    if chat_data[chat_id]['main_id'] == user_id:
        user_data = chat_data[chat_id]['users'][user_id]
        
        # Проверка кулдауна
        if user_data['last_voice_time'] and (now - user_data['last_voice_time']).total_seconds() < VOICE_COOLDOWN_SECONDS:
            return

        # Проверка минимальной длительности
        if message.voice.duration < VOICE_MIN_DURATION_SECONDS:
            bot.send_message(chat_id, f"*{random.choice(soviet_phrases['too_short'])}* ({message.voice.duration} сек)", reply_to_message_id=message.message_id)
            return

        bot.send_message(chat_id, f"*{random.choice(soviet_phrases['accept'])}*", reply_to_message_id=message.message_id)

        if user_data.get('last_voice_time'):
            delta_minutes = (now - user_data['last_voice_time']).total_seconds() / 60
            user_data['voice_deltas'].append(delta_minutes)
        
        if user_data.get('reminder_sent_at'):
            response_time_minutes = (now - user_data['reminder_sent_at']).total_seconds() / 60
            user_data['response_times'].append(response_time_minutes)
            user_data['reminder_sent_at'] = None

        user_data['count'] += 1
        user_data['last_voice_time'] = now
        user_data['voice_durations'].append(message.voice.duration)

@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in BREAK_KEYWORDS))
def handle_break_request(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_id > 0 or chat_data.get(chat_id, {}).get('main_id') != user_id: return
        
    user = chat_data[chat_id]['users'][user_id]
    if user.get('on_break'):
        return bot.reply_to(message, "Вы уже на перерыве.")

    last_break = user.get('last_break_time')
    if last_break and (datetime.datetime.now(pytz.timezone('Europe/Moscow')) - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
        remaining_time = int(BREAK_DELAY_MINUTES - (datetime.datetime.now(pytz.timezone('Europe/Moscow')) - last_break).total_seconds() / 60)
        return bot.reply_to(message, f"Следующий перерыв можно взять через {remaining_time} мин.")

    user.update({
        'on_break': True, 
        'break_start_time': datetime.datetime.now(pytz.timezone('Europe/Moscow')),
        'last_break_time': datetime.datetime.now(pytz.timezone('Europe/Moscow')),
        'breaks_count': user.get('breaks_count', 0) + 1,
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
    save_history_event(chat_id, user_id, get_username(message.from_user), "Ушел на перерыв")
    
@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in RETURN_CONFIRM_WORDS))
def handle_return_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_id > 0 or chat_data.get(chat_id, {}).get('main_id') != user_id: return
    handle_user_return(chat_id, user_id)

# ========================================
#   АНАЛИТИКА И ГЕНЕРАЦИЯ ОТЧЕТОВ
# ========================================
def generate_detailed_report(chat_id: int, data: dict) -> list:
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}): 
        return ["Главный на смене не был назначен или не проявил активности."]

    user = data['users'][main_id]
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    plan_percent = (user['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    
    report = [
        f"📋 #Итоговый_Отчет_Смены ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
        f"🏢 Чат: {get_chat_title(chat_id)}",
        f"🎤 Ведущий: {user['username']}", "---",
        f"🗣️ **Голосовых:** {user['count']} из {EXPECTED_VOICES_PER_SHIFT} ({plan_percent:.0f}%)",
        f"☕ **Перерывов:** {user['breaks_count']}",
        f"⏳ **Опозданий с перерыва:** {user['late_returns']}", "---",
        "**Статистика активности:**",
        f"📈 Средний ритм: {avg_delta:.1f} мин/ГС",
        f"🔇 Макс. пауза: {max_pause:.1f} мин.",
        f"📏 Ср. длина ГС: {avg_duration:.1f} сек."
    ]
    return report

def generate_analytical_summary(user_data: dict) -> str:
    """Генерирует прямые управленческие рекомендации."""
    plan_percent = (user_data.get('count', 0) / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    lates = user_data.get('late_returns', 0)
    
    has_long_pauses = False
    if user_data.get('voice_deltas'):
        if max(user_data['voice_deltas']) > VOICE_TIMEOUT_MINUTES * 1.5:
            has_long_pauses = True

    if plan_percent < 50:
        return f"❗️ **Критическое невыполнение плана ({plan_percent:.0f}%).** Требуется срочная беседа."
    elif plan_percent < 80 and lates > 0:
        return f"❗️ **Системные проблемы.** План не выполнен ({plan_percent:.0f}%) и есть опоздания. Рекомендуется взять сотрудника на контроль."
    elif plan_percent < 90:
        return f"⚠️ **План не выполнен ({plan_percent:.0f}%).** Необходимо выяснить причины."
    elif lates > 0:
        return f"⚠️ **Проблемы с дисциплиной.** План выполнен, но зафиксировано {lates} опоздание(й). Рекомендуется провести беседу."
    elif has_long_pauses:
        return f"✅ **Хорошая работа, но есть замечание.** План выполнен, однако были слишком длинные паузы. Стоит обратить внимание на ритмичность."
    else:
        return "✅ **Отличная работа!** Все показатели в норме. Можно ставить в пример."

# ========================================
#   ПЛАНИРОВЩИК И ЗАПУСК БОТА
# ========================================
def send_end_of_shift_report_for_chat(chat_id):
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        logging.warning(f"Попытка закрыть смену в чате {chat_id}, но активной смены нет.")
        return

    main_user_data = data['users'][data['main_id']]
    analytical_conclusion = generate_analytical_summary(main_user_data)
    
    # Сохраняем данные в Google Sheets перед отправкой отчета
    append_shift_to_google_sheet(chat_id, data, analytical_conclusion)
    
    report_lines = generate_detailed_report(chat_id, data)
    final_report = "\n".join(report_lines) + f"\n\n---\n🧠 **Рекомендация:**\n_{analytical_conclusion}_"

    try:
        bot.send_message(chat_id, final_report)
        # Дублируем отчет в чат руководства
        if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
            bot.send_message(ADMIN_REPORT_CHAT_ID, final_report)
    except Exception as e:
        logging.error(f"Не удалось отправить итоговый отчет в чате {chat_id}: {e}")
    
    # Очистка данных по завершенной смене
    if chat_id in user_history: del user_history[chat_id]
    if chat_id in chat_data: del chat_data[chat_id]
    logging.info(f"Данные смены для чата {chat_id} очищены.")

def check_for_shift_end():
    """Проверяет каждый чат на предмет окончания смены по его локальному времени."""
    for chat_id, config in list(chat_configs.items()):
        tz_name = config.get('timezone')
        end_time_str = config.get('end_time')
        if not tz_name or not end_time_str: continue

        local_tz = pytz.timezone(tz_name)
        now_local = datetime.datetime.now(local_tz)

        # Время отчета - через 1 минуту после официального конца смены
        end_time_obj = datetime.datetime.strptime(end_time_str, '%H:%M').time()
        report_time_obj = (datetime.datetime.combine(now_local.date(), end_time_obj) + datetime.timedelta(minutes=1)).time()
        
        # Если текущее время совпадает с временем отчета
        if now_local.time().strftime('%H:%M') == report_time_obj.strftime('%H:%M'):
            if chat_data.get(chat_id, {}).get('main_id'):
                # Проверяем, чтобы не отправлять отчет повторно в ту же минуту
                last_report_date = chat_data.get(chat_id, {}).get('last_report_date')
                if last_report_date != now_local.date():
                    logging.info(f"Наступило время ({report_time_obj.strftime('%H:%M')}) для отчета в чате {chat_id} (ТЗ: {tz_name}).")
                    send_end_of_shift_report_for_chat(chat_id)
                    # Помечаем, что отчет за эту дату отправлен
                    if chat_id in chat_data:
                        chat_data[chat_id]['last_report_date'] = now_local.date()

def run_scheduler():
    """Запускает планировщик задач."""
    load_chat_configs()
    schedule.every(1).minutes.do(check_for_shift_end)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.info("🤖 Бот (версия 9.0, каноничная) запущен...")
    if not all([gspread, pd]):
        logging.critical("Ключевые библиотеки (gspread, pandas) не загружены. Функциональность будет ограничена. Бот остановлен.")
    else:
        threading.Thread(target=run_scheduler, daemon=True).start()
        while True:
            try:
                bot.polling(none_stop=True, interval=0)
            except Exception as e:
                logging.error(f"Критическая ошибка polling: {e}")
                time.sleep(15)
