# -*- coding: utf-8 -*-
"""
Финальная интегрированная версия v24.0 (Production Ready):
- Объединены и полностью реализованы все функции из версий v21.0 и v23.0.
- Внедрено центральное интерактивное меню /admin для всех административных задач.
- Реализованы новые инструменты: управление контентом (/reklama), поиск проблемных зон (/problems), массовая рассылка (/broadcast).
- Проведен финальный аудит и рефакторинг всего кода для максимальной стабильности и читаемости.
- Вся функциональность финализирована и готова к работе.
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
from typing import Dict, List, Optional
from collections import Counter

# Попытка импорта ключевых библиотек
try:
    import gspread
    import pandas as pd
    import openai
except ImportError:
    logging.error("Необходимые библиотеки не найдены. Установите их: pip install gspread google-auth-oauthlib pandas openai")
    gspread, pd, openai = None, None, None

# Импорт кастомных фраз и достижений
try:
    from phrases import soviet_phrases, BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, ACHIEVEMENTS
except ImportError:
    logging.warning("Файл 'phrases.py' не найден. Используются значения по умолчанию.")
    BREAK_KEYWORDS = ["перерыв", "отдых", "обед", "покурить", "отойду"]
    RETURN_CONFIRM_WORDS = ["вернулся", "на месте", "пришел", "тут"]
    ACHIEVEMENTS = {}
    soviet_phrases = {
        "accept": ["Принято."], "too_short": ["Коротко."], "voice_reminder": ["Напоминаю."],
        "return_demand": ["Вернитесь к работе."], "pace_reminder": ["Нужно ускориться."],
        "topic_reminder": ["Не забудьте про тему: {topic}"]
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
BOSS_ID = 196614680  # Замените на реальный ID руководителя
ADMIN_REPORT_CHAT_ID = -1002645821302 # Замените на реальный ID чата для отчетов
CHAT_CONFIG_FILE = 'chat_configs.json'
AD_TEMPLATES_FILE = 'ad_templates.json'

# --- Параметры смены ---
EXPECTED_VOICES_PER_SHIFT = 15
VOICE_TIMEOUT_MINUTES = 40
VOICE_MIN_DURATION_SECONDS = 7
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60

# --- Ссылка на Google Таблицу ---
GOOGLE_SHEET_LINK_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_KEY}/edit#gid=0" if GOOGLE_SHEET_KEY else ""
GOOGLE_SHEET_LINK_TEXT = "АНАЛИЗ РАБОТЫ ВЕДУЩИХ"

# --- Карта часовых поясов ---
TIMEZONE_MAP = {
    "-1": "Europe/Kaliningrad", "0": "Europe/Moscow", "+1": "Europe/Samara", "+2": "Asia/Yekaterinburg",
    "+3": "Asia/Omsk", "+4": "Asia/Krasnoyarsk", "+5": "Asia/Irkutsk", "+6": "Asia/Yakutsk",
    "+7": "Asia/Vladivostok", "+8": "Asia/Magadan", "+9": "Asia/Kamchatka"
}

# --- Инициализация сервисов ---
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False, parse_mode="Markdown")
client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None
if not client:
    logging.warning("OPENAI_API_KEY не найден, анализ речи будет отключен.")

# --- Глобальные переменные ---
chat_data: Dict[int, dict] = {}
user_history: Dict[int, List[str]] = {}
chat_configs: Dict[int, dict] = {}
ad_templates: Dict[str, dict] = {}
user_states: Dict[int, dict] = {} # Для хранения состояний пользователей (например, ожидание ввода)

# ========================================
#   БЛОК УПРАВЛЕНИЯ КОНФИГУРАЦИЕЙ И ДАННЫМИ
# ========================================
def load_json_data(filepath, default_value={}):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки файла {filepath}: {e}")
    return default_value

def save_json_data(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения файла {filepath}: {e}")
        return False

def load_all_data():
    global chat_configs, ad_templates
    chat_configs = {int(k): v for k, v in load_json_data(CHAT_CONFIG_FILE, {}).items()}
    ad_templates = load_json_data(AD_TEMPLATES_FILE, {})
    logging.info(f"Загружено {len(chat_configs)} конфигов чатов и {len(ad_templates)} брендов с шаблонами.")

# ========================================
#   БЛОК РАБОТЫ С GOOGLE SHEETS
# ========================================
def get_sheet() -> Optional[gspread.Worksheet]:
    if not all([gspread, GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON]):
        logging.error("gspread не импортирован или переменные окружения для Google не заданы.")
        return None
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        return gc.open_by_key(GOOGLE_SHEET_KEY).sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error("Таблица с ключом не найдена. Проверьте ID и права доступа.")
        return None
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

def create_sheet_header_if_needed(worksheet: gspread.Worksheet):
    try:
        if worksheet.acell('A1').value is None:
            headers = ["Дата", "ID Чата", "Название Чата", "Бренд", "Город", "ID Ведущего", "Тег Ведущего", "Голосовых (шт)", "План (шт)", "Выполнение (%)", "Перерывов (шт)", "Опозданий (шт)", "Средний ритм (мин)", "Макс. пауза (мин)", "Ср. длина ГС (сек)", "Рекомендация", "Затронутые темы"]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:Q1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
            logging.info("Создана шапка в Google Таблице.")
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(chat_id: int, data: dict, analytical_conclusion: str):
    worksheet = get_sheet()
    if not worksheet: return
    create_sheet_header_if_needed(worksheet)
    
    main_id = data.get('main_id')
    user_data = data.get('users', {}).get(main_id)
    if not user_data: return

    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
    
    # Расчет статистики с проверкой на пустые списки
    avg_delta = sum(user_data.get('voice_deltas', [])) / len(user_data['voice_deltas']) if user_data.get('voice_deltas') else 0
    max_pause = max(user_data.get('voice_deltas', [0]))
    avg_duration = sum(user_data.get('voice_durations', [])) / len(user_data['voice_durations']) if user_data.get('voice_durations') else 0
    
    chat_config = chat_configs.get(chat_id, {})
    brand = chat_config.get('brand', 'N/A')
    city = chat_config.get('city', 'N/A')
    
    ad_counts = Counter(user_data.get('recognized_ads', []))
    recognized_ads_str = ", ".join([f"{ad} (x{count})" for ad, count in ad_counts.items()]) or "Нет данных"

    row_data = [
        data.get('shift_start', now_moscow).strftime('%d.%m.%Y'), chat_id, get_chat_title(chat_id),
        brand, city, main_id, user_data.get('username', 'N/A'), user_data.get('count', 0), 
        shift_goal, f"{plan_percent:.0f}%", user_data.get('breaks_count', 0), 
        user_data.get('late_returns', 0), f"{avg_delta:.1f}", f"{max_pause:.1f}", 
        f"{avg_duration:.1f}", analytical_conclusion, recognized_ads_str
    ]
    try:
        worksheet.append_row(row_data, value_input_option='USER_ENTERED')
        logging.info(f"Данные по смене в чате {chat_id} успешно добавлены в Google Таблицу.")
    except Exception as e:
        logging.error(f"Не удалось добавить данные в Google Таблицу: {e}")

# ========================================
#   ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================
def is_admin(user_id: int, chat_id: int) -> bool:
    if user_id == BOSS_ID: return True
    if chat_id > 0: return False # Админ-команды не работают в ЛС
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    except Exception: return False

def admin_required(func):
    @wraps(func)
    def wrapper(message):
        if not is_admin(message.from_user.id, message.chat.id):
            return bot.reply_to(message, "⛔️ Эта команда доступна только администраторам чата.")
        return func(message)
    return wrapper

def boss_required(func):
    @wraps(func)
    def wrapper(message):
        if message.from_user.id != BOSS_ID:
            return bot.reply_to(message, "⛔️ Эта команда доступна только главному руководителю.")
        return func(message)
    return wrapper

def get_username(user: types.User) -> str:
    return f"@{user.username}" if user.username else user.first_name

def get_chat_title(chat_id: int) -> str:
    try:
        return bot.get_chat(chat_id).title or str(chat_id)
    except Exception:
        return str(chat_id)

def init_user_data(user_id: int, username: str) -> dict:
    return {
        'username': username, 'count': 0, 'on_break': False, 'breaks_count': 0, 
        'late_returns': 0, 'last_voice_time': None, 'last_break_time': None, 
        'break_start_time': None, 'voice_timeout_reminder_sent': False,
        'last_break_reminder_time': None, 'pace_reminder_sent': False, 
        'topic_reminder_sent': False, 'recognized_ads': [], 
        'voice_deltas': [], 'voice_durations': [], 'achievements': []
    }

def init_shift_data(chat_id: int):
    chat_data[chat_id] = {
        'main_id': None, 'users': {}, 'main_username': 'N/A',
        'shift_start': datetime.datetime.now(pytz.timezone('Europe/Moscow')),
        'shift_goal': chat_configs.get(chat_id, {}).get('default_goal', EXPECTED_VOICES_PER_SHIFT)
    }

def handle_user_return(chat_id: int, user_id: int):
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
    save_history_event(chat_id, user_id, user['username'], f"Вернулся с перерыва (длительность {break_duration_minutes:.1f} мин)")

def save_history_event(chat_id: int, user_id: int, username: str, event_description: str):
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

# ========================================
#   АНАЛИЗ РЕЧИ ЧЕРЕЗ OPENAI
# ========================================
def analyze_voice_content(audio_path: str, chat_id: int) -> List[str]:
    if not client or not ad_templates: return []
    
    chat_config = chat_configs.get(chat_id, {})
    brand = chat_config.get("brand")
    city = chat_config.get("city")
    
    if not brand or not city:
        logging.warning(f"Для чата {chat_id} не определен бренд/город. Пропуск анализа.")
        return []
        
    templates_for_location = ad_templates.get(brand, {}).get(city)
    if not templates_for_location:
        logging.warning(f"В ad_templates.json не найдены шаблоны для '{brand}' в городе '{city}'.")
        return []

    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        recognized_text = transcript.text
        logging.info(f"Распознанный текст: '{recognized_text}'")
        if not recognized_text.strip(): return []

        system_prompt = ("Ты — ассистент, который находит в тексте диктора упоминания рекламных шаблонов из списка. В ответ верни названия ВСЕХ подходящих шаблонов, каждое с новой строки. Если совпадений нет, верни 'None'.")
        ad_list_for_prompt = "\n".join([f"- {name}: '{text}'" for name, text in templates_for_location.items()])
        user_prompt = f"Текст диктора: '{recognized_text}'.\n\nСписок шаблонов:\n{ad_list_for_prompt}\n\nКакие шаблоны были упомянуты?"

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0
        )
        analysis_result_text = completion.choices[0].message.content.strip()

        if analysis_result_text == 'None':
            logging.info("GPT не нашел совпадений с шаблонами.")
            return []

        found_templates = [line.strip() for line in analysis_result_text.splitlines() if line.strip() in templates_for_location]
        if found_templates:
            logging.info(f"GPT определил совпадения: {found_templates}")
        return found_templates
            
    except Exception as e:
        logging.error(f"Ошибка при обработке аудио через OpenAI: {e}")
        try:
            if BOSS_ID:
                bot.send_message(BOSS_ID, f"❗️ Ошибка анализа речи OpenAI в чате {get_chat_title(chat_id)}:\n`{e}`")
        except Exception as send_e:
            logging.error(f"Не удалось отправить личное сообщение об ошибке: {send_e}")
        return []

def process_audio_and_save_result(file_path: str, user_data: dict, chat_id: int):
    try:
        ad_names = analyze_voice_content(file_path, chat_id)
        if ad_names:
            user_data['recognized_ads'].extend(ad_names)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# ========================================
#   ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ
# ========================================
@bot.message_handler(content_types=['voice'])
def handle_voice_message(message: types.Message):
    chat_id = message.chat.id
    if chat_id > 0: return # Бот работает только в группах

    user_id = message.from_user.id
    username = get_username(message.from_user)
    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

    # Инициализация данных, если их нет
    if chat_id not in chat_data: init_shift_data(chat_id)
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)
    
    is_new_main = False
    # Автоматическое назначение ведущего по первому ГС
    if chat_data[chat_id].get('main_id') is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        is_new_main = True

    # Обработка голоса только от главного на смене
    if chat_data[chat_id]['main_id'] == user_id:
        if is_new_main:
            bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")
            save_history_event(chat_id, user_id, username, "Стал главным (первое ГС)")
        
        user_data = chat_data[chat_id]['users'][user_id]
        
        # Проверка на кулдаун
        if not is_new_main and user_data.get('last_voice_time'):
            time_since_last = (now_moscow - user_data['last_voice_time']).total_seconds()
            if time_since_last < VOICE_COOLDOWN_SECONDS:
                remaining = int(VOICE_COOLDOWN_SECONDS - time_since_last)
                bot.reply_to(message, f"Слишком часто! Пауза {remaining} сек.", disable_notification=True)
                return
        
        # Проверка на длительность
        if message.voice.duration < VOICE_MIN_DURATION_SECONDS:
            bot.reply_to(message, f"*{random.choice(soviet_phrases.get('too_short'))}* ({message.voice.duration} сек)")
            return
            
        bot.send_message(chat_id, f"*{random.choice(soviet_phrases.get('accept'))}*", reply_to_message_id=message.message_id)
        
        if user_data.get('last_voice_time'):
            delta_minutes = (now_moscow - user_data['last_voice_time']).total_seconds() / 60
            user_data['voice_deltas'].append(delta_minutes)
            
        user_data['count'] += 1
        user_data['last_voice_time'] = now_moscow
        user_data['voice_durations'].append(message.voice.duration)
        user_data['voice_timeout_reminder_sent'] = False # Сброс флага напоминания

        # Анализ речи в отдельном потоке
        if client:
            try:
                file_info = bot.get_file(message.voice.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                file_path = f"voice_{message.message_id}.ogg"
                with open(file_path, 'wb') as new_file:
                    new_file.write(downloaded_file)
                threading.Thread(target=process_audio_and_save_result, args=(file_path, user_data, chat_id)).start()
            except Exception as e:
                logging.error(f"Ошибка при скачивании аудиофайла: {e}")

@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower().split() for word in BREAK_KEYWORDS))
def handle_break_request(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id > 0 or chat_data.get(chat_id, {}).get('main_id') != user_id: return
    
    user_data = chat_data[chat_id]['users'][user_id]
    if user_data.get('on_break'):
        return bot.reply_to(message, "Вы уже на перерыве.")
    
    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    last_break = user_data.get('last_break_time')
    if last_break and (now_moscow - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
        remaining_time = int(BREAK_DELAY_MINUTES - (now_moscow - last_break).total_seconds() / 60)
        return bot.reply_to(message, f"Следующий перерыв можно взять через {remaining_time} мин.")
        
    user_data.update({
        'on_break': True, 'break_start_time': now_moscow,
        'last_break_time': now_moscow, 'breaks_count': user_data['breaks_count'] + 1,
        'last_break_reminder_time': None
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
    save_history_event(chat_id, user_id, get_username(message.from_user), "Ушел на перерыв")
    
@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower().split() for word in RETURN_CONFIRM_WORDS))
def handle_return_message(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id > 0 or chat_data.get(chat_id, {}).get('main_id') != user_id: return
    
    handle_user_return(chat_id, user_id)

# ========================================
#   ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
# ========================================
@bot.message_handler(commands=['start', 'старт'])
def handle_start(message: types.Message):
    chat_id = message.chat.id
    if chat_id > 0: return bot.reply_to(message, "Эта команда работает только в групповом чате.")
    
    from_user = message.from_user
    username = get_username(from_user)
    
    if chat_id not in chat_data: init_shift_data(chat_id)
    if from_user.id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][from_user.id] = init_user_data(from_user.id, username)
        
    if chat_data[chat_id].get('main_id') is not None:
        main_username = chat_data[chat_id].get('main_username', 'Неизвестно')
        return bot.reply_to(message, f"Смена уже занята. Текущий главный: {main_username}.")
        
    chat_data[chat_id]['main_id'] = from_user.id
    chat_data[chat_id]['main_username'] = username
    bot.send_message(chat_id, f"👑 {username}, вы заступили на смену! Удачи!")
    save_history_event(chat_id, from_user.id, username, "Стал главным на смене (команда /start)")

@bot.message_handler(commands=['промежуточный', 'check'])
def handle_check(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    data = chat_data.get(chat_id)
    
    if not data or not data.get('main_id'):
        return bot.reply_to(message, "Смена в этом чате еще не началась.")
        
    main_user_id = data['main_id']
    if user_id != main_user_id:
        return bot.reply_to(message, f"Эту команду может использовать только текущий главный на смене: {data.get('main_username')}.")

    main_user_data = data.get('users', {}).get(main_user_id)
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (main_user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
    
    report_lines = [
        f"📋 *Промежуточный отчет для вас* ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
        f"🗣️ **Голосовых:** {main_user_data['count']} из {shift_goal} ({plan_percent:.0f}%)",
        f"☕ **Перерывов:** {main_user_data['breaks_count']}",
        f"⏳ **Опозданий с перерыва:** {main_user_data['late_returns']}"
    ]
    
    ad_counts = Counter(main_user_data.get('recognized_ads', []))
    if ad_counts:
        report_lines.append("\n**📝 Анализ контента:**")
        for ad, count in ad_counts.items():
            report_lines.append(f"✔️ {ad} (x{count})")
            
    bot.reply_to(message, "\n".join(report_lines))

@bot.message_handler(commands=['сводка'])
def my_total_stats(message: types.Message):
    if not pd: return bot.reply_to(message, "Модуль для анализа данных (pandas) не загружен.")
    
    user_id = message.from_user.id
    username = get_username(message.from_user)
    bot.reply_to(message, f"📊 Собираю вашу общую статистику из Google Таблицы, {username}. Минутку...")
    
    worksheet = get_sheet()
    if not worksheet: return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице.")
        
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty or 'ID Ведущего' not in df.columns:
            return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")
        
        df['ID Ведущего'] = pd.to_numeric(df['ID Ведущего'], errors='coerce')
        user_df = df[df['ID Ведущего'] == user_id].copy() # Используем .copy() для избежания Warning'ов
        
        if user_df.empty:
            return bot.send_message(message.chat.id, f"{username}, не найдено ваших смен в общей статистике.")
        
        # Конвертируем колонки в числовой формат, заменяя ошибки на 0
        numeric_cols = ['Голосовых (шт)', 'Перерывов (шт)', 'Опозданий (шт)']
        for col in numeric_cols:
            user_df[col] = pd.to_numeric(user_df[col], errors='coerce').fillna(0)

        total_shifts = len(user_df)
        total_voices = user_df['Голосовых (шт)'].sum()
        total_breaks = user_df['Перерывов (шт)'].sum()
        total_lates = user_df['Опозданий (шт)'].sum()
        
        report_text = (
            f"⭐️ **Общая статистика для {username}** ⭐️\n\n"
            f"👑 **Всего смен отработано:** {total_shifts}\n"
            f"🗣️ **Всего голосовых записано:** {int(total_voices)}\n"
            f"☕️ **Всего перерывов:** {int(total_breaks)}\n"
            f"⏳ **Всего опозданий с перерыва:** {int(total_lates)}"
        )
        bot.send_message(message.chat.id, report_text)
    except Exception as e:
        logging.error(f"Ошибка анализа Google Sheets для /сводка: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при анализе данных из таблицы.")

@bot.message_handler(commands=['help', 'справка'])
def handle_help(message: types.Message):
    is_user_admin = is_admin(message.from_user.id, message.chat.id)
    
    help_text_lines = [
        "📖 *Справка по командам бота*",
        "\n---",
        "**👤 Основные команды для ведущего:**",
        "`/start` или `/старт` — Занять смену, если она свободна.",
        "`/промежуточный` или `/check` — Показать свой личный отчет по текущей смене.",
        "`/сводка` — Посмотреть свою общую статистику за все время.",
        "Для перерыва просто напишите в чат `перерыв`, `обед` или `отдых`.",
        "Для возвращения — `вернулся`, `на месте`.",
    ]
    
    if is_user_admin:
        help_text_lines.extend([
            "\n---",
            "**🛠️ Команды для администраторов:**",
            "`/admin` — Открыть интерактивное меню для управления ботом.",
            "Все основные действия (проверка статуса, настройка, отчеты, рассылка и т.д.) выполняются через кнопки в этом меню."
        ])

    bot.reply_to(message, "\n".join(help_text_lines))
        
# ========================================
#   НОВЫЕ АДМИНИСТРАТИВНЫЕ ИНСТРУМЕНТЫ (МЕНЮ /admin)
# ========================================
@bot.message_handler(commands=['admin'])
@admin_required
def handle_admin_menu(message: types.Message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    is_boss = message.from_user.id == BOSS_ID
    
    markup.add(
        types.InlineKeyboardButton("📊 Статус смены", callback_data="admin_shift_status"),
        types.InlineKeyboardButton("📈 Общий рейтинг", callback_data="admin_analyze_all"),
        types.InlineKeyboardButton("📝 Упр. рекламой", callback_data="admin_manage_ads"),
        types.InlineKeyboardButton("🚨 Проблемные зоны", callback_data="admin_find_problems"),
        types.InlineKeyboardButton("⚙️ Настройка чата", callback_data="admin_chat_setup"),
        types.InlineKeyboardButton("🔄 Перезапуск смены", callback_data="admin_restart_shift"),
        types.InlineKeyboardButton("➡️ Отчет досрочно", callback_data="admin_force_report"),
        types.InlineKeyboardButton("📜 Выгрузить лог", callback_data="admin_export_history")
    )
    # Кнопка рассылки только для BOSS_ID
    if is_boss:
        markup.add(types.InlineKeyboardButton("📢 Рассылка (BOSS)", callback_data="admin_broadcast"))
        
    bot.send_message(message.chat.id, "Добро пожаловать в панель администратора!", reply_markup=markup)

# Обработчик всех нажатий на кнопки в админ-меню
@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callbacks(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id
    
    # Проверяем права доступа для callback'ов
    if not is_admin(user_id, chat_id):
        return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
    
    action = call.data.split('_', 1)[1]
    
    if action == 'shift_status':
        show_shift_status(call)
    elif action == 'analyze_all':
        show_overall_rating(call)
    elif action == 'manage_ads':
        show_ad_brands_menu(call.message, is_main_menu=True)
    elif action == 'find_problems':
        find_problem_zones(call)
    elif action == 'chat_setup':
        show_setup_menu(call)
    elif action == 'restart_shift':
        restart_shift(call)
    elif action == 'force_report':
        force_report(call)
    elif action == 'export_history':
        export_history(call)
    elif action == 'broadcast':
        if user_id != BOSS_ID: # Двойная проверка
            return bot.answer_callback_query(call.id, "⛔️ Только для BOSS!", show_alert=True)
        request_broadcast_text(call.message)
    elif action == 'main_menu':
         bot.edit_message_text("Добро пожаловать в панель администратора!", chat_id, message_id, reply_markup=call.message.reply_markup)
    
    bot.answer_callback_query(call.id) # Подтверждаем получение callback

# --- Реализация функций админ-меню ---

def show_shift_status(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        return bot.send_message(chat_id, "Смена в этом чате еще не началась.")
        
    user_data = data.get('users', {}).get(data['main_id'])
    if not user_data:
        return bot.send_message(chat_id, "В текущей смене нет данных о ведущем.")
    
    report_text = get_full_report_text(chat_id, user_data, data)
    bot.send_message(chat_id, report_text)
    
def get_full_report_text(chat_id: int, user_data: dict, data: dict) -> str:
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    plan_percent = (user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
    avg_delta = sum(user_data['voice_deltas']) / len(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    max_pause = max(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    avg_duration = sum(user_data['voice_durations']) / len(user_data['voice_durations']) if user_data['voice_durations'] else 0
    
    report_lines = [
        f"📋 **Промежуточный отчет по смене** ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
        f"🎤 **Ведущий:** {user_data['username']}",
        "\n---",
        "**📊 Основная Статистика**",
        f"**Голосовых:** {user_data['count']} из {shift_goal} ({plan_percent:.0f}%)",
        f"**Перерывов:** {user_data['breaks_count']}",
        f"**Опозданий:** {user_data['late_returns']}",
        "\n---",
        "**📈 Аналитика Активности**",
        f"**Средний ритм:** {avg_delta:.1f} мин/ГС" if avg_delta else "**Средний ритм:** Н/Д",
        f"**Макс. пауза:** {max_pause:.1f} мин." if max_pause else "**Макс. пауза:** Н/Д",
        f"**Ср. длина ГС:** {avg_duration:.1f} сек." if avg_duration else "**Ср. длина ГС:** Н/Д"
    ]
    
    ad_counts = Counter(user_data.get('recognized_ads', []))
    if ad_counts:
        report_lines.append("\n---\n**📝 Анализ Контента**")
        for ad, count in ad_counts.items():
            report_lines.append(f"✔️ {ad} (x{count})")
            
    return "\n".join(report_lines)

def show_overall_rating(call: types.CallbackQuery):
    if not pd: return bot.send_message(call.message.chat.id, "Модуль для анализа данных (pandas) не загружен.")
    bot.send_message(call.message.chat.id, "📊 Анализирую общую статистику из Google Таблицы. Это может занять время...")
    
    worksheet = get_sheet()
    if not worksheet: return bot.send_message(call.message.chat.id, "Не удалось подключиться к Google Таблице.")
        
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty or 'Тег Ведущего' not in df.columns:
            return bot.send_message(call.message.chat.id, "В таблице пока нет данных для анализа.")
        
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
        summary = summary.sort_values(by='avg_voices', ascending=False).reset_index(drop=True)
        
        report_lines = ["📊 **Общая сводка по всем сотрудникам**", "_(На основе данных из Google Sheets)_\n"]
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        for i, row in summary.iterrows():
            rank_icon = medals.get(i, f" {i+1}.")
            report_lines.append(
                f"*{rank_icon}* {row['Тег Ведущего']} — *Ср. ГС:* `{row['avg_voices']:.1f}` | *Опоздания:* `{row['lateness_percent']:.0f}%` | *Смен:* `{row['total_shifts']}`"
            )
        bot.send_message(call.message.chat.id, "\n".join(report_lines))
    except Exception as e:
        logging.error(f"Ошибка анализа Google Sheets для /analyze: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при анализе данных из таблицы.")

def find_problem_zones(call: types.CallbackQuery):
    if not pd: return bot.send_message(call.message.chat.id, "Модуль для анализа данных (pandas) не загружен.")
    bot.send_message(call.message.chat.id, "🚨 Ищу проблемные зоны в Google Таблице...")
    
    worksheet = get_sheet()
    if not worksheet: return bot.send_message(call.message.chat.id, "Не удалось подключиться к Google Таблице.")
        
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty: return bot.send_message(call.message.chat.id, "В таблице нет данных.")
        
        # Преобразование в числовой формат
        numeric_cols = ['Выполнение (%)', 'Опозданий (шт)', 'Макс. пауза (мин)']
        for col in numeric_cols:
            # Убираем '%' и преобразуем
            df[col] = df[col].astype(str).str.replace('%', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=numeric_cols, inplace=True)
        
        # Фильтры для "проблем"
        low_perf = df[df['Выполнение (%)'] < 80]
        latecomers = df[df['Опозданий (шт)'] > 0]
        long_pauses = df[df['Макс. пауза (мин)'] > (VOICE_TIMEOUT_MINUTES * 1.5)]
        
        report_lines = ["🚨 **Анализ проблемных зон**\n"]
        
        if not low_perf.empty:
            report_lines.append("*📉 Низкое выполнение плана (<80%):*")
            for _, row in low_perf.iterrows():
                report_lines.append(f" - {row['Тег Ведущего']} ({row['Дата']}): *{row['Выполнение (%)']:.0f}%*")
        
        if not latecomers.empty:
            report_lines.append("\n*⏳ Опоздания с перерывов:*")
            for _, row in latecomers.iterrows():
                report_lines.append(f" - {row['Тег Ведущего']} ({row['Дата']}): *{int(row['Опозданий (шт)'])}* раз(а)")

        if not long_pauses.empty:
            report_lines.append("\n*⏱️ Слишком долгие паузы:*")
            for _, row in long_pauses.iterrows():
                report_lines.append(f" - {row['Тег Ведущего']} ({row['Дата']}): макс. пауза *{row['Макс. пауза (мин)']:.0f} мин*")
        
        if len(report_lines) == 1:
            bot.send_message(call.message.chat.id, "✅ Проблемных зон по основным критериям не найдено. Отличная работа!")
        else:
            bot.send_message(call.message.chat.id, "\n".join(report_lines))
    except Exception as e:
        logging.error(f"Ошибка поиска проблемных зон: {e}")
        bot.send_message(call.message.chat.id, f"Произошла ошибка при анализе: {e}")

def request_broadcast_text(message: types.Message):
    msg = bot.send_message(message.chat.id, "Введите текст для массовой рассылки всем чатам. Для отмены введите /cancel.")
    bot.register_next_step_handler(msg, process_broadcast_text)

def process_broadcast_text(message: types.Message):
    if message.text == '/cancel':
        return bot.send_message(message.chat.id, "Рассылка отменена.")
    if message.from_user.id != BOSS_ID: return
    
    text_to_send = message.text
    if not text_to_send: return bot.reply_to(message, "Текст рассылки не может быть пустым.")
    
    sent_count = 0
    total_chats = len(list(chat_configs.keys()))
    bot.send_message(message.chat.id, f"Начинаю рассылку в {total_chats} чатов...")
    
    for chat_id_str in chat_configs.keys():
        try:
            bot.send_message(int(chat_id_str), f"❗️ **Важное объявление от руководства:**\n\n{text_to_send}")
            sent_count += 1
            time.sleep(0.1) # Небольшая задержка, чтобы не превышать лимиты Telegram
        except Exception as e:
            logging.error(f"Не удалось отправить рассылку в чат {chat_id_str}: {e}")
    
    bot.send_message(message.chat.id, f"✅ Рассылка успешно отправлена в {sent_count} из {total_chats} чатов.")

def restart_shift(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    if chat_id in chat_data and chat_data[chat_id].get('main_id') is not None:
        init_shift_data(chat_id)
        bot.send_message(chat_id, "🔄 Смена перезапущена. Текущий главный и план сброшены.")
        save_history_event(chat_id, call.from_user.id, get_username(call.from_user), "Перезапустил смену")
    else:
        bot.send_message(chat_id, "Активной смены в этом чате и так не было.")

def force_report(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "⏳ Формирую финальный отчет досрочно...")
    send_end_of_shift_report_for_chat(chat_id)

def export_history(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    history = user_history.get(chat_id)
    if not history:
        return bot.send_message(chat_id, "История событий для текущей смены пуста.")
    try:
        filename = f"history_{chat_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"История событий для чата: {get_chat_title(chat_id)}\n" + "="*40 + "\n" + "\n".join(history))
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="Лог событий текущей смены.")
        os.remove(filename)
    except Exception as e:
        logging.error(f"Ошибка при выгрузке истории: {e}")
        bot.send_message(chat_id, "Произошла ошибка при создании файла истории.")
        
# ========================================
#   УПРАВЛЕНИЕ РЕКЛАМОЙ (из /admin)
# ========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('ad_'))
def handle_ad_callbacks(call: types.CallbackQuery):
    if not is_admin(call.from_user.id, call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
    
    parts = call.data.split('_')
    action = parts[1]
    
    if action == "brand":
        brand = parts[2]
        show_ad_cities_menu(call.message, brand)
    elif action == "city":
        brand = parts[2]
        city = parts[3]
        show_ad_actions_menu(call.message, brand, city)
    elif action == "view":
        brand, city = parts[2], parts[3]
        view_ad_templates(call.message, brand, city)
    elif action == "addform":
        brand, city = parts[2], parts[3]
        request_ad_template_to_add(call.message, brand, city)
    elif action == "delform":
        brand, city = parts[2], parts[3]
        show_templates_for_deletion(call.message, brand, city)
    elif action == "delete":
        brand, city, tpl_key = parts[2], parts[3], parts[4]
        delete_ad_template(call, brand, city, tpl_key)
    elif action == 'backtobrand':
        show_ad_brands_menu(call.message, is_main_menu=False)
    elif action == 'backtocity':
        brand = parts[2]
        show_ad_cities_menu(call.message, brand)

    bot.answer_callback_query(call.id)

def show_ad_brands_menu(message: types.Message, is_main_menu: bool):
    markup = types.InlineKeyboardMarkup(row_width=2)
    brands = list(ad_templates.keys())
    for brand in brands:
        markup.add(types.InlineKeyboardButton(brand.upper(), callback_data=f"ad_brand_{brand}"))
    markup.add(types.InlineKeyboardButton("➕ Добавить новый бренд", callback_data="ad_addbrand_form"))
    if is_main_menu:
        markup.add(types.InlineKeyboardButton("« Назад в меню", callback_data="admin_main_menu"))
    
    bot.edit_message_text("Выберите бренд для управления рекламой:", message.chat.id, message.message_id, reply_markup=markup)

def show_ad_cities_menu(message: types.Message, brand: str):
    markup = types.InlineKeyboardMarkup(row_width=2)
    cities = list(ad_templates.get(brand, {}).keys())
    for city in cities:
        markup.add(types.InlineKeyboardButton(city.capitalize(), callback_data=f"ad_city_{brand}_{city}"))
    markup.add(types.InlineKeyboardButton("➕ Добавить новый город", callback_data=f"ad_addcity_form_{brand}"))
    markup.add(types.InlineKeyboardButton("« Назад к брендам", callback_data="ad_backtobrand"))
    bot.edit_message_text(f"Бренд: *{brand.upper()}*\nВыберите город:", message.chat.id, message.message_id, reply_markup=markup)
    
def show_ad_actions_menu(message: types.Message, brand: str, city: str):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👁️‍🗨️ Просмотреть шаблоны", callback_data=f"ad_view_{brand}_{city}"),
        types.InlineKeyboardButton("➕ Добавить шаблон", callback_data=f"ad_addform_{brand}_{city}"),
        types.InlineKeyboardButton("➖ Удалить шаблон", callback_data=f"ad_delform_{brand}_{city}"),
        types.InlineKeyboardButton("« Назад к городам", callback_data=f"ad_backtocity_{brand}")
    )
    bot.edit_message_text(f"Бренд: *{brand.upper()}* / Город: *{city.capitalize()}*\nВыберите действие:", message.chat.id, message.message_id, reply_markup=markup)

def view_ad_templates(message: types.Message, brand: str, city: str):
    templates = ad_templates.get(brand, {}).get(city, {})
    if not templates:
        text = "Шаблонов для этого города пока нет."
    else:
        text_lines = [f"📄 **Шаблоны для {brand.upper()} / {city.capitalize()}**\n"]
        for name, content in templates.items():
            text_lines.append(f"🔹 *{name}*:\n`{content}`\n")
        text = "\n".join(text_lines)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

def request_ad_template_to_add(message: types.Message, brand: str, city: str):
    user_id = message.chat.id # Используем chat.id для простоты, т.к. это админ
    user_states[user_id] = {"state": "awaiting_ad_template", "brand": brand, "city": city}
    bot.send_message(message.chat.id, "Отправьте сообщение в формате:\n\n`Название шаблона`\n`Текст шаблона...`\n\nДля отмены введите /cancel")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get("state") == "awaiting_ad_template")
def receive_ad_template_to_add(message: types.Message):
    user_id = message.from_user.id
    if message.text == '/cancel':
        del user_states[user_id]
        return bot.send_message(message.chat.id, "Добавление шаблона отменено.")
    
    try:
        name, text = message.text.split('\n', 1)
        name = name.strip()
        text = text.strip()
        if not name or not text: raise ValueError
        
        state_data = user_states[user_id]
        brand, city = state_data['brand'], state_data['city']
        
        if brand not in ad_templates: ad_templates[brand] = {}
        if city not in ad_templates[brand]: ad_templates[brand][city] = {}
        
        ad_templates[brand][city][name] = text
        if save_json_data(AD_TEMPLATES_FILE, ad_templates):
            bot.send_message(message.chat.id, f"✅ Шаблон *'{name}'* успешно добавлен для *{brand.upper()}/{city.capitalize()}*.")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка сохранения файла шаблонов.")
            
        del user_states[user_id]
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат. Пожалуйста, отправьте сообщение в формате:\n\n`Название шаблона`\n`Текст шаблона...`")
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {e}")
        if user_id in user_states: del user_states[user_id]

def show_templates_for_deletion(message: types.Message, brand: str, city: str):
    templates = ad_templates.get(brand, {}).get(city, {})
    if not templates:
        return bot.edit_message_text("Здесь нет шаблонов для удаления.", message.chat.id, message.message_id)
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    for tpl_key in templates.keys():
        markup.add(types.InlineKeyboardButton(f"❌ {tpl_key}", callback_data=f"ad_delete_{brand}_{city}_{tpl_key}"))
    markup.add(types.InlineKeyboardButton("« Назад", callback_data=f"ad_city_{brand}_{city}"))
    bot.edit_message_text("Выберите шаблон для удаления:", message.chat.id, message.message_id, reply_markup=markup)

def delete_ad_template(call: types.CallbackQuery, brand: str, city: str, tpl_key: str):
    if tpl_key in ad_templates.get(brand, {}).get(city, {}):
        del ad_templates[brand][city][tpl_key]
        if save_json_data(AD_TEMPLATES_FILE, ad_templates):
            bot.answer_callback_query(call.id, f"Шаблон '{tpl_key}' удален.", show_alert=True)
            show_templates_for_deletion(call.message, brand, city) # Обновить список
        else:
            bot.answer_callback_query(call.id, "Ошибка сохранения!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "Этот шаблон уже удален.", show_alert=True)
        
# ========================================
#   НАСТРОЙКА ЧАТА (из /admin)
# ========================================

def show_setup_menu(call: types.CallbackQuery):
    chat_id = call.message.chat.id
    config = chat_configs.get(chat_id, {})
    
    text = (
        f"⚙️ **Настройки чата: {get_chat_title(chat_id)}**\n\n"
        f"*Бренд:* `{config.get('brand', 'Не задан')}`\n"
        f"*Город:* `{config.get('city', 'Не задан')}`\n"
        f"*Часовой пояс:* `{config.get('timezone', 'Не задан (МСК по умолч.)')}`\n"
        f"*График смены:* `{config.get('start_time', 'Н/Д')} - {config.get('end_time', 'Н/Д')}`\n"
        f"*План по ГС:* `{config.get('default_goal', EXPECTED_VOICES_PER_SHIFT)}`\n\n"
        "Отправьте команду для изменения параметра:"
    )
    
    bot.send_message(chat_id, text, parse_mode="Markdown")
    bot.send_message(chat_id, "`/setup <бренд> <город>`\n`/set_timezone +3`\n`/тайминг 19:00 04:00`\n`/setgoal <число>`")

@bot.message_handler(commands=['setup'])
@admin_required
def handle_setup(message):
    chat_id = message.chat.id
    try:
        _, brand, city = message.text.split()
        brand, city = brand.lower(), city.lower()
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id].update({'brand': brand, 'city': city})
        save_json_data(CHAT_CONFIG_FILE, chat_configs)
        bot.reply_to(message, f"✅ Чат успешно настроен!\n**Бренд:** `{brand}`\n**Город:** `{city}`")
    except ValueError:
        bot.reply_to(message, "Неверный формат. Используйте: `/setup <бренд> <город>`")

@bot.message_handler(commands=['set_timezone'])
@admin_required
def set_timezone(message):
    chat_id = message.chat.id
    try:
        offset = message.text.split()[1]
        tz_name = TIMEZONE_MAP.get(offset)
        if not tz_name:
            return bot.reply_to(message, f"❌ Неверный формат смещения. Доступно: {list(TIMEZONE_MAP.keys())}")
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id]['timezone'] = tz_name
        save_json_data(CHAT_CONFIG_FILE, chat_configs)
        local_time = datetime.datetime.now(pytz.timezone(tz_name)).strftime('%H:%M:%S')
        bot.send_message(chat_id, f"✅ Часовой пояс установлен на *{tz_name}* (МСК{offset}).\nТекущее время: *{local_time}*.")
    except IndexError:
        bot.reply_to(message, "Пример использования: `/set_timezone +3`")

@bot.message_handler(commands=['тайминг'])
@admin_required
def set_shift_timing(message):
    chat_id = message.chat.id
    try:
        _, start_time_str, end_time_str = message.text.split()
        datetime.datetime.strptime(start_time_str, '%H:%M')
        datetime.datetime.strptime(end_time_str, '%H:%M')
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id].update({'start_time': start_time_str, 'end_time': end_time_str})
        save_json_data(CHAT_CONFIG_FILE, chat_configs)
        bot.send_message(chat_id, f"✅ График смены установлен: с *{start_time_str}* до *{end_time_str}*.")
    except (IndexError, ValueError):
        bot.reply_to(message, "Неверный формат. Пример: `/тайминг 19:00 04:00`")

@bot.message_handler(commands=['setgoal'])
@admin_required
def set_default_goal(message):
    chat_id = message.chat.id
    try:
        goal = int(message.text.split()[1])
        if goal <= 0: raise ValueError
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id]['default_goal'] = goal
        save_json_data(CHAT_CONFIG_FILE, chat_configs)
        bot.send_message(chat_id, f"✅ План по умолчанию для новых смен в этом чате установлен: *{goal}* ГС.")
    except (IndexError, ValueError):
        bot.reply_to(message, "Неверный формат. Укажите положительное число. Пример: `/setgoal 20`")
        
# ========================================
#   АНАЛИТИКА И ГЕНЕРАЦИЯ ОТЧЕТОВ
# ========================================
def generate_analytical_summary(user_data: dict, shift_goal: int) -> str:
    plan_percent = (user_data.get('count', 0) / shift_goal * 100) if shift_goal > 0 else 0
    lates = user_data.get('late_returns', 0)
    
    has_long_pauses = False
    if user_data.get('voice_deltas'):
        if max(user_data['voice_deltas']) > VOICE_TIMEOUT_MINUTES * 1.5:
            has_long_pauses = True

    if plan_percent < 50:
        return f"❗️ Критическое невыполнение плана ({plan_percent:.0f}%). Требуется срочная беседа."
    if plan_percent < 80 and lates > 0:
        return f"❗️ Системные проблемы. План не выполнен ({plan_percent:.0f}%) и есть опоздания. Рекомендуется взять сотрудника на контроль."
    if plan_percent < 90:
        return f"⚠️ План не выполнен ({plan_percent:.0f}%). Необходимо выяснить причины."
    if lates > 0:
        return f"⚠️ Проблемы с дисциплиной. План выполнен, но зафиксировано {lates} опоздание(й). Рекомендуется провести беседу."
    if has_long_pauses:
        return f"✅ Хорошая работа, но есть замечание. План выполнен, однако были слишком длинные паузы. Стоит обратить внимание на ритмичность."
    
    return "✅ Отличная работа! Все показатели в норме. Можно ставить в пример."

def generate_detailed_report(chat_id: int, data: dict) -> list:
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}):
        return ["Главный на смене не был назначен или не проявил активности."]
        
    user = data['users'][main_id]
    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    
    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    plan_percent = (user['count'] / shift_goal * 100) if shift_goal > 0 else 0
    
    report_lines = [
        f"📋 **#ОТЧЕТ_ТЕКСТ_ВЕДУЩЕГО** ({data.get('shift_start', datetime.datetime.now()).strftime('%d.%m.%Y')})",
        f"🎤 **Ведущий:** {user['username']}",
        "\n---",
        "**📊 Основная Статистика**",
        f"**Голосовых:** {user['count']} из {shift_goal} ({plan_percent:.0f}%)",
        f"**Перерывов:** {user['breaks_count']}",
        f"**Опозданий:** {user['late_returns']}",
        "\n---",
        "**📈 Аналитика Активности**",
        f"**Средний ритм:** {avg_delta:.1f} мин/ГС" if avg_delta else "**Средний ритм:** Н/Д",
        f"**Макс. пауза:** {max_pause:.1f} мин." if max_pause else "**Макс. пауза:** Н/Д",
        f"**Ср. длина ГС:** {avg_duration:.1f} сек." if avg_duration else "**Ср. длина ГС:** Н/Д"
    ]
    
    ad_counts = Counter(user.get('recognized_ads', []))
    if ad_counts:
        report_lines.append("\n---\n**📝 Анализ Контента**")
        for ad, count in ad_counts.items():
            report_lines.append(f"✔️ {ad} (x{count})")
            
    return report_lines
    
# ========================================
#   ПЛАНИРОВЩИК И ФОНОВЫЕ ЗАДАЧИ
# ========================================
def send_end_of_shift_report_for_chat(chat_id: int):
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        logging.warning(f"Попытка закрыть смену в чате {chat_id}, но активной смены нет.")
        try:
            bot.send_message(chat_id, "Не удалось сформировать отчет: смена не была активна.")
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление о неактивной смене в чат {chat_id}: {e}")
        return
    
    main_user_data = data.get('users', {}).get(data.get('main_id'))
    if not main_user_data:
        logging.warning(f"Не найдены данные по ведущему в чате {chat_id}")
        return

    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    analytical_conclusion = generate_analytical_summary(main_user_data, shift_goal)
    append_shift_to_google_sheet(chat_id, data, analytical_conclusion)
    
    report_lines = generate_detailed_report(chat_id, data)
    final_report_text = "\n".join(report_lines)
    
    final_report_with_recommendation = final_report_text + f"\n\n---\n🧠 **Рекомендация:**\n_{analytical_conclusion}_"
    try:
        bot.send_message(chat_id, final_report_with_recommendation)
    except Exception as e:
        logging.error(f"Не удалось отправить отчет в рабочий чат {chat_id}: {e}")

    if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
        try:
            link_markdown = f"[{GOOGLE_SHEET_LINK_TEXT}]({GOOGLE_SHEET_LINK_URL})" if GOOGLE_SHEET_LINK_URL else ""
            admin_report_header = f"📍 *Отчет из чата: {get_chat_title(chat_id)}*\n"
            admin_report = f"{admin_report_header}{final_report_with_recommendation}\n\n{link_markdown}"
            bot.send_message(ADMIN_REPORT_CHAT_ID, admin_report)
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат руководства: {e}")
    
    if chat_id in user_history: del user_history[chat_id]
    if chat_id in chat_data: del chat_data[chat_id]
    logging.info(f"Данные смены для чата {chat_id} очищены.")

def check_user_activity():
    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    for chat_id, data in list(chat_data.items()):
        if not data.get('main_id'): continue
        main_id = data['main_id']
        user_data = data.get('users', {}).get(main_id)
        if not user_data: continue

        if user_data.get('on_break'):
            break_start_time = user_data.get('break_start_time')
            if break_start_time and (now_moscow - break_start_time).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                last_reminder = user_data.get('last_break_reminder_time')
                if not last_reminder or (now_moscow - last_reminder).total_seconds() > 120:
                    try:
                        bot.send_message(chat_id, f"@{user_data['username']}, {random.choice(soviet_phrases.get('return_demand'))}")
                        user_data['last_break_reminder_time'] = now_moscow
                    except Exception as e:
                        logging.error(f"Не удалось отправить напоминание о перерыве в чат {chat_id}: {e}")
            continue

        last_voice_time = user_data.get('last_voice_time')
        if last_voice_time:
            inactive_minutes = (now_moscow - last_voice_time).total_seconds() / 60
            if inactive_minutes > VOICE_TIMEOUT_MINUTES and not user_data.get('voice_timeout_reminder_sent'):
                try:
                    bot.send_message(chat_id, f"@{user_data['username']}, {random.choice(soviet_phrases.get('voice_reminder'))}")
                    user_data['voice_timeout_reminder_sent'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о ГС в чат {chat_id}: {e}")

def check_for_shift_end():
    for chat_id, config in list(chat_configs.items()):
        tz_name = config.get('timezone', 'Europe/Moscow')
        end_time_str = config.get('end_time')
        if not end_time_str: continue
        
        try:
            local_tz = pytz.timezone(tz_name)
            now_local = datetime.datetime.now(local_tz)
            end_time_obj = datetime.datetime.strptime(end_time_str, '%H:%M').time()
            report_time_obj = (datetime.datetime.combine(now_local.date(), end_time_obj) + datetime.timedelta(minutes=1)).time()
            
            if chat_data.get(chat_id, {}).get('main_id'):
                if now_local.time().strftime('%H:%M') == report_time_obj.strftime('%H:%M'):
                    if chat_data[chat_id].get('last_report_date') != now_local.date():
                        logging.info(f"Наступило время ({report_time_obj.strftime('%H:%M')}) для отчета в чате {chat_id} (ТЗ: {tz_name}).")
                        send_end_of_shift_report_for_chat(chat_id)
                        if chat_id in chat_data:
                            chat_data[chat_id]['last_report_date'] = now_local.date()
        except Exception as e:
            logging.error(f"Ошибка в check_for_shift_end для чата {chat_id}: {e}")

def run_scheduler():
    """Эта функция содержит все фоновые задачи, которые должны выполняться регулярно."""
    schedule.every(1).minutes.do(check_for_shift_end)
    schedule.every(1).minutes.do(check_user_activity)
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"Критическая ошибка в цикле планировщика: {e}")
        time.sleep(1)

# ========================================
#   ЗАПУСК БОТА
# ========================================
if __name__ == '__main__':
    logging.info("🤖 Бот (версия 24.1, Production Ready) запускается...")
    
    # Проверка наличия ключевых библиотек
    if not all([gspread, pd, openai]):
        logging.critical("Ключевые библиотеки (gspread, pandas, openai) не загружены. Функциональность будет ограничена.")
    
    # Загружаем все конфигурации при старте
    load_all_data()
    
    # Запускаем планировщик фоновых задач в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logging.info("Планировщик фоновых задач запущен.")
    
    # Запускаем бота в режиме бесконечного опроса с автоматическим перезапуском
    logging.info("Бот запущен и готов к работе.")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
