# -*- coding: utf-8 -*-
"""
Финальная версия v17.0 (с Напоминаниями):
- Добавлены активные напоминания для ведущего.
- Бот напоминает о затянувшемся перерыве каждые 2 минуты.
- Бот напоминает о долгой паузе (40 мин без ГС).
- Все тексты для напоминаний берутся из phrases.py.
- Вся предыдущая функциональность сохранена.
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
from collections import Counter

# Попытка импорта ключевых библиотек
try:
    import gspread
    import pandas as pd
    import openai
except ImportError:
    logging.error("Необходимые библиотеки не найдены. Установите их: pip install gspread google-auth-oauthlib pandas openai")
    gspread = None
    pd = None
    openai = None

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
        "return_demand": ["Товарищ, пора возвращаться к работе! Коллектив ждет."],
        "voice_reminder": ["Вы давно не выходили в эфир. Не нарушайте план!"]
    }

# ========================================
#   НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

# --- Переменные окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")


# --- ID и конфиги ---
BOSS_ID = 196614680
ADMIN_REPORT_CHAT_ID = -1002645821302
CHAT_CONFIG_FILE = 'chat_configs.json'

# --- Параметры смены ---
EXPECTED_VOICES_PER_SHIFT = 80
VOICE_TIMEOUT_MINUTES = 40
VOICE_MIN_DURATION_SECONDS = 3
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60

# --- Ссылка на Google Таблицу для отчетов ---
GOOGLE_SHEET_LINK_URL = "https://docs.google.com/spreadsheets/d/1Zj25HCub7GxSNmXeMv5bkSi7fvPll_2iOkP4GR2gYWs/edit?gid=0#gid=0"
GOOGLE_SHEET_LINK_TEXT = "АНАЛИЗ РАБОТЫ ВЕДУЩИХ"

# --- Карта часовых поясов ---
TIMEZONE_MAP = {
    "-1": "Europe/Kaliningrad", "0": "Europe/Moscow", "+1": "Europe/Samara",
    "+2": "Asia/Yekaterinburg", "+3": "Asia/Omsk", "+4": "Asia/Krasnoyarsk",
    "+5": "Asia/Irkutsk", "+6": "Asia/Yakutsk", "+7": "Asia/Vladivostok",
    "+8": "Asia/Magadan", "+9": "Asia/Kamchatka"
}

# --- Инициализация сервисов ---
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False, parse_mode="Markdown")

# Инициализация клиента OpenAI
if OPENAI_API_KEY and openai:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None
    logging.warning("OPENAI_API_KEY не найден, анализ речи будет отключен.")

# --- Глобальные переменные ---
chat_data: Dict[int, dict] = {}
user_history: Dict[int, List[str]] = {}
chat_configs: Dict[int, dict] = {}

# --- Загрузка шаблонов для анализа ---
AD_TEMPLATES = {}
try:
    with open('ad_templates_perm_july.json', 'r', encoding='utf-8') as f:
        AD_TEMPLATES = json.load(f)
    logging.info(f"Успешно загружено {len(AD_TEMPLATES)} рекламных шаблонов.")
except FileNotFoundError:
    logging.warning("Файл 'ad_templates_perm_july.json' не найден. Анализ контента будет невозможен.")
except json.JSONDecodeError:
    logging.error("Ошибка в синтаксисе файла 'ad_templates_perm_july.json'.")


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
    if not gspread or not GOOGLE_SHEET_KEY:
        logging.error("gspread не импортирован или GOOGLE_SHEET_KEY не задан.")
        return None
    try:
        creds_json_str = GOOGLE_CREDENTIALS_JSON
        if not creds_json_str:
            logging.error("Переменная окружения GOOGLE_CREDENTIALS_JSON не найдена!")
            return None
        
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_KEY)
        return spreadsheet.sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error("Таблица с ключом не найдена. Проверьте ID и права доступа.")
        return None
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

def create_sheet_header_if_needed(worksheet):
    try:
        if worksheet.acell('A1').value is None:
            headers = [
                "Дата", "ID Чата", "Название Чата", "ID Ведущего", "Тег Ведущего",
                "Голосовых (шт)", "План (шт)", "Выполнение (%)", "Перерывов (шт)",
                "Опозданий (шт)", "Средний ритм (мин)", "Макс. пауза (мин)", "Ср. длина ГС (сек)",
                "Рекомендация", "Затронутые темы"
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:O1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
            logging.info("Создана шапка в Google Таблице.")
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(chat_id, data, analytical_conclusion):
    worksheet = get_sheet()
    if not worksheet:
        logging.error("Выгрузка в Google Sheets невозможна: лист не найден.")
        return

    create_sheet_header_if_needed(worksheet)
    main_id = data.get('main_id')
    user_data = data.get('users', {}).get(main_id)
    if not user_data: return

    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
    avg_delta = sum(user_data['voice_deltas']) / len(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    max_pause = max(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    avg_duration = sum(user_data['voice_durations']) / len(user_data['voice_durations']) if user_data['voice_durations'] else 0
    
    ad_counts = Counter(user_data.get('recognized_ads', []))
    recognized_ads_str = ", ".join([f"{ad} (x{count})" for ad, count in ad_counts.items()]) or "Нет данных"

    row_data = [
        data.get('shift_start', now).strftime('%d.%m.%Y'), chat_id, get_chat_title(chat_id),
        main_id, user_data['username'], user_data['count'], shift_goal,
        f"{plan_percent:.0f}%", user_data['breaks_count'], user_data['late_returns'],
        f"{avg_delta:.1f}", f"{max_pause:.1f}", f"{avg_duration:.1f}",
        analytical_conclusion, recognized_ads_str
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
        'voice_durations': [], 'break_start_time': None,
        'recognized_ads': [],
        'voice_timeout_reminder_sent': False,
        'last_break_reminder_time': None
    }

def init_shift_data(chat_id):
    chat_data[chat_id] = {
        'main_id': None, 
        'users': {}, 
        'shift_start': datetime.datetime.now(pytz.timezone('Europe/Moscow')),
        'shift_goal': EXPECTED_VOICES_PER_SHIFT
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
#   АНАЛИЗ РЕЧИ ЧЕРЕЗ OPENAI
# ========================================
def analyze_voice_content(audio_path: str) -> str:
    if not client or not AD_TEMPLATES:
        return None
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
              model="whisper-1", 
              file=audio_file
            )
        recognized_text = transcript.text
        logging.info(f"Распознанный текст: '{recognized_text}'")

        if not recognized_text.strip():
            return None

        system_prompt = "Ты — ассистент, который определяет, какой из рекламных текстов произнес диктор. В ответ дай только название рекламы из списка или слово 'None', если совпадений нет."
        ad_list_for_prompt = "\n".join([f"- {name}: '{text}'" for name, text in AD_TEMPLATES.items()])
        user_prompt = f"Вот текст от диктора: '{recognized_text}'.\n\nВот список рекламных шаблонов:\n{ad_list_for_prompt}\n\nКакая реклама была произнесена? Ответь только названием или 'None'."

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1
        )
        analysis_result = completion.choices[0].message.content.strip()

        if analysis_result in AD_TEMPLATES:
            logging.info(f"GPT определил совпадение: {analysis_result}")
            return analysis_result
        else:
            logging.info("GPT не нашел точного совпадения с шаблонами.")
            return None
    except Exception as e:
        logging.error(f"Ошибка при обработке аудио через OpenAI: {e}")
        return None

def process_audio_and_save_result(file_path, user_data):
    try:
        ad_name = analyze_voice_content(file_path)
        if ad_name:
            user_data['recognized_ads'].append(ad_name)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


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
        init_shift_data(chat_id)
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
        init_shift_data(chat_id)
        bot.reply_to(message, "🔄 Смена перезапущена. Текущий главный и план сброшены.")
        save_history_event(chat_id, message.from_user.id, get_username(message.from_user), "Перезапустил смену")
    else:
        bot.reply_to(message, "Активной смены в этом чате и так не было.")

@bot.message_handler(commands=['промежуточный', 'check'])
def handle_check(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        return bot.reply_to(message, "Смена в этом чате еще не началась.")

    main_user_id = data['main_id']
    main_user_data = data.get('users', {}).get(main_user_id)

    if user_id != main_user_id:
        return bot.reply_to(message, f"Эту команду может использовать только текущий главный на смене: {main_user_data.get('username', 'Неизвестно')}.")

    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (main_user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
    
    report_text = (
        f"📋 Промежуточный отчет для вас ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})\n\n"
        f"🗣️ Голосовых: {main_user_data['count']} из {shift_goal} ({plan_percent:.0f}%)\n"
        f"☕ Перерывов: {main_user_data['breaks_count']}\n"
        f"⏳ Опозданий с перерыва: {main_user_data['late_returns']}"
    )
    bot.reply_to(message, report_text)

@bot.message_handler(commands=['checkadmin'])
@admin_required
def handle_checkadmin(message):
    chat_id = message.chat.id
    try:
        target_username = message.text.split()[1]
        if not target_username.startswith('@'):
            target_username = '@' + target_username
    except IndexError:
        return bot.reply_to(message, "Неверный формат. Используйте: `/checkadmin @username`")

    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        return bot.reply_to(message, "Смена в этом чате еще не началась.")

    main_user_data = data.get('users', {}).get(data['main_id'])
    if main_user_data['username'].lower() != target_username.lower():
        return bot.reply_to(message, f"Указанный пользователь {target_username} не является главным на текущей смене. Сейчас на смене: {main_user_data['username']}")

    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (main_user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
    report_lines = [
        f"📋 Промежуточный отчет ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
        f"🏢 Чат: {get_chat_title(chat_id)}",
        f"🎤 Ведущий: {main_user_data['username']}", "---",
        f"🗣️ Голосовых: {main_user_data['count']} из {shift_goal} ({plan_percent:.0f}%)",
        f"☕ Перерывов: {main_user_data['breaks_count']}",
        f"⏳ Опозданий с перерыва: {main_user_data['late_returns']}"
    ]
    ad_counts = Counter(main_user_data.get('recognized_ads', []))
    if ad_counts:
        report_lines.append("\nАнализ контента:")
        for ad, count in ad_counts.items():
            report_lines.append(f"✔️ {ad} (x{count})")
    final_report = "\n".join(report_lines)
    bot.reply_to(message, final_report)

@bot.message_handler(commands=['limited', 'лимит'])
@admin_required
def handle_limit(message):
    chat_id = message.chat.id
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        return bot.reply_to(message, "Нельзя установить лимит, так как смена еще не началась.")
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            raise IndexError
        target_limit = int(parts[1])
        if target_limit <= 0:
            return bot.reply_to(message, "План должен быть положительным числом.")

        data['shift_goal'] = target_limit
        bot.reply_to(message, f"✅ Новый план на текущую смену установлен: *{target_limit}* голосовых сообщений.")
        save_history_event(chat_id, message.from_user.id, get_username(message.from_user), f"Установил новый план: {target_limit} ГС")

    except IndexError:
        return bot.reply_to(message, "Неверный формат. Используйте: `/лимит <число>`")
    except ValueError:
        return bot.reply_to(message, "Укажите корректное число после команды.")
    
@bot.message_handler(commands=['отчет'])
@admin_required
def admin_get_final_report(message):
    chat_id = message.chat.id
    send_end_of_shift_report_for_chat(chat_id)

@bot.message_handler(commands=['сводка'])
def my_total_stats(message):
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
    if not pd: return bot.reply_to(message, "Модуль для анализа данных (pandas) не загружен.")
    bot.reply_to(message, "📊 Анализирую общую статистику из Google Таблицы. Это может занять время...")
    worksheet = get_sheet()
    if not worksheet:
        return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице для анализа.")
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty or 'ID Ведущего' not in df.columns:
            return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")
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
        bot.send_message(message.chat.id, f"✅ Часовой пояс для этого чата установлен на *{tz_name}* (МСК{offset}).\nТекущее время: *{local_time}*.")
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
    bot.reply_to(message, "⚙️ Запускаю тест соединения с Google Sheets...")
    worksheet = get_sheet() 
    if worksheet:
        try:
            sheet_title = worksheet.spreadsheet.title
            bot.send_message(message.chat.id, 
                f"✅ *УСПЕХ!*\n\n"
                f"Соединение с Google Sheets установлено.\n"
                f"Бот успешно получил доступ к таблице: *'{sheet_title}'*."
            )
        except Exception as e:
            bot.send_message(message.chat.id, 
                f"❗️*ОШИБКА НА ЭТАПЕ ЧТЕНИЯ!*\n\n"
                f"Подключение установлено, но не удалось прочитать данные.\n"
                f"Детали: `{e}`"
            )
    else:
        bot.send_message(message.chat.id, 
            f"❌ *ПРОВАЛ!*\n\n"
            f"Не удалось подключиться к Google Sheets. Проверьте лог."
        )

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = """
*Справка по командам бота*

*Общие Команды*
`/start` — Назначить себя главным на смене.
`/промежуточный` (или `/check`) — Показать свой промежуточный отчет.
`/сводка` — Посмотреть свою личную статистику за все время.
`/перерыв` или `/обед` — Уйти на перерыв.

*Административные Команды*
`/limited <число>` — Установить план по ГС на текущую смену.
`/checkadmin @username` — Показать отчет по текущему ведущему.
`/restart` — Перезапустить смену, сбросив главного.
`/отчет` — Сформировать и отправить финальный отчет по смене.
`/analyze` — Показать рейтинг всех сотрудников из Google Таблиц.
`/выгрузка` — Выгрузить историю событий текущей смены.
`/set_timezone +N` — Установить часовой пояс для чата.
`/тайминг 19:00 04:00` — Установить время начала и окончания смены.
`/testsheet` — Проверить соединение с Google Sheets.
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
        init_shift_data(chat_id)
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)
    if chat_data[chat_id].get('main_id') is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")
        save_history_event(chat_id, user_id, username, "Стал главным (первое ГС)")

    if chat_data[chat_id]['main_id'] == user_id:
        user_data = chat_data[chat_id]['users'][user_id]
        
        if user_data.get('last_voice_time'):
            time_since_last = (now - user_data['last_voice_time']).total_seconds()
            if time_since_last < VOICE_COOLDOWN_SECONDS:
                remaining = int(VOICE_COOLDOWN_SECONDS - time_since_last)
                bot.reply_to(message, f"Слишком часто! Следующее ГС можно записать через {remaining} сек.", disable_notification=True)
                return
        
        if message.voice.duration < VOICE_MIN_DURATION_SECONDS:
            bot.send_message(chat_id, f"*{random.choice(soviet_phrases['too_short'])}* ({message.voice.duration} сек)", reply_to_message_id=message.message_id)
            return
            
        bot.send_message(chat_id, f"*{random.choice(soviet_phrases['accept'])}*", reply_to_message_id=message.message_id)
        
        if user_data.get('last_voice_time'):
            delta_minutes = (now - user_data['last_voice_time']).total_seconds() / 60
            user_data['voice_deltas'].append(delta_minutes)
            
        user_data['count'] += 1
        user_data['last_voice_time'] = now
        user_data['voice_durations'].append(message.voice.duration)
        user_data['voice_timeout_reminder_sent'] = False

        file_path = None
        try:
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_path = f"voice_{message.message_id}.ogg"
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            threading.Thread(target=process_audio_and_save_result, args=(file_path, user_data)).start()
        except Exception as e:
            logging.error(f"Ошибка при скачивании аудиофайла: {e}")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

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
        'last_break_reminder_time': None
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
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    plan_percent = (user['count'] / shift_goal * 100) if shift_goal > 0 else 0
    report = [
        f"📋 #ОТЧЕТ_ТЕКСТ_ВЕДУЩЕГО ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
        f"🏢 Чат: {get_chat_title(chat_id)}",
        f"🎤 Ведущий: {user['username']}", "---",
        f"🗣️ Голосовых: {user['count']} из {shift_goal} ({plan_percent:.0f}%)",
        f"☕ Перерывов: {user['breaks_count']}",
        f"⏳ Опозданий с перерыва: {user['late_returns']}", "---",
        "Статистика активности:",
        f"📈 Средний ритм: {avg_delta:.1f} мин/ГС",
        f"🔇 Макс. пауза: {max_pause:.1f} мин.",
        f"📏 Ср. длина ГС: {avg_duration:.1f} сек."
    ]
    
    ad_counts = Counter(user.get('recognized_ads', []))
    if ad_counts:
        report.append("\nАнализ контента:")
        for ad, count in ad_counts.items():
            report.append(f"✔️ {ad} (x{count})")
            
    return report

def generate_analytical_summary(user_data: dict, shift_goal: int) -> str:
    plan_percent = (user_data.get('count', 0) / shift_goal * 100) if shift_goal > 0 else 0
    lates = user_data.get('late_returns', 0)
    has_long_pauses = False
    if user_data.get('voice_deltas') and user_data['voice_deltas']:
        if max(user_data['voice_deltas']) > VOICE_TIMEOUT_MINUTES * 1.5:
            has_long_pauses = True
    if plan_percent < 50:
        return f"❗️ Критическое невыполнение плана ({plan_percent:.0f}%). Требуется срочная беседа."
    elif plan_percent < 80 and lates > 0:
        return f"❗️ Системные проблемы. План не выполнен ({plan_percent:.0f}%) и есть опоздания. Рекомендуется взять сотрудника на контроль."
    elif plan_percent < 90:
        return f"⚠️ План не выполнен ({plan_percent:.0f}%). Необходимо выяснить причины."
    elif lates > 0:
        return f"⚠️ Проблемы с дисциплиной. План выполнен, но зафиксировано {lates} опоздание(й). Рекомендуется провести беседу."
    elif has_long_pauses:
        return f"✅ Хорошая работа, но есть замечание. План выполнен, однако были слишком длинные паузы. Стоит обратить внимание на ритмичность."
    else:
        return "✅ Отличная работа! Все показатели в норме. Можно ставить в пример."


# ========================================
#   ПЛАНИРОВЩИК И ЗАПУСК БОТА
# ========================================
def send_end_of_shift_report_for_chat(chat_id):
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        logging.warning(f"Попытка закрыть смену в чате {chat_id}, но активной смены нет.")
        return
    
    main_user_data = data.get('users', {}).get(data.get('main_id'))
    if not main_user_data:
        logging.warning(f"Не найдены данные по ведущему в чате {chat_id}")
        return

    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    analytical_conclusion = generate_analytical_summary(main_user_data, shift_goal)
    append_shift_to_google_sheet(chat_id, data, analytical_conclusion)
    
    report_lines = generate_detailed_report(chat_id, data)
    final_report = "\n".join(report_lines) + f"\n\n---\n🧠 **Рекомендация:**\n_{analytical_conclusion}_"

    try:
        bot.send_message(chat_id, final_report)
        if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
            link_markdown = f"[{GOOGLE_SHEET_LINK_TEXT}]({GOOGLE_SHEET_LINK_URL})"
            admin_report = final_report + f"\n\n---\n📊 {link_markdown}"
            bot.send_message(ADMIN_REPORT_CHAT_ID, admin_report, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не удалось отправить итоговый отчет в чате {chat_id}: {e}")
    
    if chat_id in user_history: del user_history[chat_id]
    if chat_id in chat_data: del chat_data[chat_id]
    logging.info(f"Данные смены для чата {chat_id} очищены.")

def check_user_activity():
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    for chat_id, data in list(chat_data.items()):
        if not data.get('main_id'):
            continue

        main_id = data['main_id']
        user_data = data.get('users', {}).get(main_id)
        if not user_data:
            continue

        # 1. Проверка затянувшегося перерыва
        if user_data.get('on_break'):
            break_start_time = user_data.get('break_start_time')
            if break_start_time:
                break_duration_minutes = (now - break_start_time).total_seconds() / 60
                if break_duration_minutes > BREAK_DURATION_MINUTES:
                    last_reminder = user_data.get('last_break_reminder_time')
                    if not last_reminder or (now - last_reminder).total_seconds() > 120:
                        try:
                            bot.send_message(chat_id, f"@{user_data['username']}, {random.choice(soviet_phrases['return_demand'])}")
                            user_data['last_break_reminder_time'] = now
                        except Exception as e:
                            logging.error(f"Не удалось отправить напоминание о перерыве в чат {chat_id}: {e}")
            continue

        # 2. Проверка долгого отсутствия голосовых
        last_voice_time = user_data.get('last_voice_time')
        if last_voice_time:
            inactive_minutes = (now - last_voice_time).total_seconds() / 60
            if inactive_minutes > VOICE_TIMEOUT_MINUTES and not user_data.get('voice_timeout_reminder_sent'):
                try:
                    bot.send_message(chat_id, f"@{user_data['username']}, {random.choice(soviet_phrases['voice_reminder'])}")
                    user_data['voice_timeout_reminder_sent'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о ГС в чат {chat_id}: {e}")

def check_for_shift_end():
    for chat_id, config in list(chat_configs.items()):
        tz_name = config.get('timezone')
        end_time_str = config.get('end_time')
        if not tz_name or not end_time_str: continue
        local_tz = pytz.timezone(tz_name)
        now_local = datetime.datetime.now(local_tz)
        end_time_obj = datetime.datetime.strptime(end_time_str, '%H:%M').time()
        report_time_obj = (datetime.datetime.combine(now_local.date(), end_time_obj) + datetime.timedelta(minutes=1)).time()
        if now_local.time().strftime('%H:%M') == report_time_obj.strftime('%H:%M'):
            if chat_data.get(chat_id, {}).get('main_id'):
                last_report_date = chat_data.get(chat_id, {}).get('last_report_date')
                if last_report_date != now_local.date():
                    logging.info(f"Наступило время ({report_time_obj.strftime('%H:%M')}) для отчета в чате {chat_id} (ТЗ: {tz_name}).")
                    send_end_of_shift_report_for_chat(chat_id)
                    if chat_id in chat_data:
                        chat_data[chat_id]['last_report_date'] = now_local.date()

def run_scheduler():
    load_chat_configs()
    schedule.every(1).minutes.do(check_for_shift_end)
    schedule.every(1).minutes.do(check_user_activity)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.info("🤖 Бот (версия 17.0, с Напоминаниями) запущен...")
    if not all([gspread, pd, openai]):
        logging.critical("Ключевые библиотеки (gspread, pandas, openai) не загружены. Функциональность будет ограничена.")
    else:
        threading.Thread(target=run_scheduler, daemon=True).start()
        while True:
            try:
                bot.polling(none_stop=True, interval=0)
            except Exception as e:
                logging.error(f"Критическая ошибка polling: {e}")
                time.sleep(15)
