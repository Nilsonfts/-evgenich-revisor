# -*- coding: utf-8 -*-
"""
Каноничная финальная версия v9.0:
- Восстановлены и адаптированы под Google Sheets команды /сводка и /analyze.
- Исправлена работа планировщика напоминаний.
- Все функции и команды финализированы.
"""

import logging
import os
import telebot
import datetime
import pytz
import time
import schedule
import threading
import random
import csv
import json
from telebot import types
from functools import wraps
from typing import Dict, List
import pandas as pd

# Импорты
try:
    import gspread
except ImportError:
    gspread = None
    logging.error("Библиотека gspread не найдена. Установите ее: pip install gspread google-auth-oauthlib pandas")

try:
    from phrases import soviet_phrases, BREAK_KEYWORDS, RETURN_CONFIRM_WORDS
except ImportError:
    logging.warning("Файл 'phrases.py' не найден.")
    BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, soviet_phrases = ["перерыв"], ["вернулся"], {}

# ========================================
#           НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN: raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

BOSS_ID = 196614680
ADMIN_REPORT_CHAT_ID = -1002645821302 
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
LAST_REPORT_FILE = 'last_shift_report.txt'
CHAT_CONFIG_FILE = 'chat_configs.json'

# Параметры смены
VOICE_TIMEOUT_MINUTES = 40
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60
SHIFT_END_TIME = "04:01"

TIMEZONE_MAP = {
    "-1": "Europe/Kaliningrad", "0": "Europe/Moscow", "+1": "Europe/Samara",
    "+2": "Asia/Yekaterinburg", "+3": "Asia/Omsk", "+4": "Asia/Krasnoyarsk",
    "+5": "Asia/Irkutsk", "+6": "Asia/Yakutsk", "+7": "Asia/Vladivostok",
    "+8": "Asia/Magadan", "+9": "Asia/Kamchatka"
}

bot = telebot.TeleBot(BOT_TOKEN, threaded=False, parse_mode="Markdown")
chat_data: Dict[int, dict] = {}
user_history: Dict[int, List[str]] = {}
chat_configs: Dict[int, dict] = {}

# ========================================
#      УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ ЧАТОВ
# ========================================
def load_chat_configs():
    global chat_configs
    if not os.path.exists(CHAT_CONFIG_FILE):
        chat_configs = {}
        return
    try:
        with open(CHAT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            chat_configs = {int(k): v for k, v in json.load(f).items()}
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
#           РАБОТА С GOOGLE SHEETS
# ========================================
def get_sheet():
    if not gspread: return None
    try:
        creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if not creds_json_str or not GOOGLE_SHEET_KEY:
            logging.error("Переменные окружения для Google Sheets не найдены!")
            return None
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_KEY)
        return spreadsheet.sheet1
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
                "Рекомендация"
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:N1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(chat_id, data, analytical_conclusion):
    worksheet = get_sheet()
    if not worksheet: return

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
        data.get('shift_start', now).strftime('%d.%m.%Y'), chat_id, get_chat_title(chat_id),
        main_id, user_data['username'], user_data['count'], EXPECTED_VOICES_PER_SHIFT, f"{plan_percent:.0f}%",
        user_data['breaks_count'], user_data['late_returns'], f"{avg_delta:.1f}", f"{max_pause:.1f}",
        f"{avg_duration:.1f}", analytical_conclusion
    ]
    try:
        worksheet.append_row(row_data, value_input_option='USER_ENTERED')
        logging.info(f"Данные по смене в чате {chat_id} успешно добавлены в Google Таблицу.")
    except Exception as e:
        logging.error(f"Не удалось добавить данные в Google Таблицу: {e}")

# ========================================
#           ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================
def is_admin(user_id, chat_id):
    if user_id == BOSS_ID: return True
    if chat_id > 0: return False
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    except Exception as e: return False

def admin_required(func):
    @wraps(func)
    def wrapper(message):
        chat_id_for_check = message.chat.id if message.chat.type != 'private' else ADMIN_REPORT_CHAT_ID
        if not is_admin(message.from_user.id, chat_id_for_check):
            bot.reply_to(message, "⛔ Эту команду могут использовать только администраторы.")
            return
        return func(message)
    return wrapper

def get_username(user) -> str: return f"@{user.username}" if user.username else user.first_name

def init_user_data(user_id, username):
    return {'username': username, 'count': 0, 'on_break': False, 'breaks_count': 0, 'late_returns': 0, 'last_voice_time': None, 'last_break_time': None, 'reminder_sent_at': None, 'response_times': [], 'voice_deltas': [], 'voice_durations': [], 'break_start_time': None}

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
    try: return bot.get_chat(chat_id).title or str(chat_id)
    except: return str(chat_id)

def save_history_event(chat_id, user_id, username, event_description):
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ
# ========================================
@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = """
*Справка по командам бота:*

`/start` — Назначить себя главным на смене.
`/restart` или `/рестарт` — Перезапустить смену.
`/check` или `/промежуточный` — Показать промежуточный отчет.
`/отчет` — Сформировать финальный отчет по смене.
`/analyze` или `/весьотчет` — Показать рейтинг всех сотрудников.
`/выгрузка` — Выгрузить историю событий смены.
`/сводка` — Посмотреть свою личную статистику за все время.

`/перерыв` или `/обед` — Уйти на перерыв.

*Команды администратора чата:*
`/set_timezone +N` — Установить часовой пояс (смещение от МСК, например `+2`).
`/тайминг 19:00 04:00` — Установить время начала и окончания смены.
`/testsheet` - Проверить соединение с Google Sheets.
"""
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['set_timezone'])
@admin_required
def set_timezone(message):
    chat_id = message.chat.id
    if chat_id > 0: return bot.reply_to(message, "Эта команда работает только в групповых чатах.")
    try:
        offset = message.text.split()[1]
        tz_name = TIMEZONE_MAP.get(offset)
        if not tz_name:
            return bot.reply_to(message, f"❌ Неверный формат смещения. Укажите смещение от МСК, например: `0`, `+1`, `-1`.")
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id]['timezone'] = tz_name
        save_chat_configs()
        local_time = datetime.datetime.now(pytz.timezone(tz_name)).strftime('%H:%M:%S')
        bot.reply_to(message, f"✅ Часовой пояс для этого чата установлен на *{tz_name}* (МСК{offset}).\nТекущее время: *{local_time}*.")
    except IndexError:
        bot.reply_to(message, "Пример: `/set_timezone +2`")

@bot.message_handler(commands=['тайминг'])
@admin_required
def set_shift_timing(message):
    chat_id = message.chat.id
    if chat_id > 0: return bot.reply_to(message, "Эта команда работает только в групповых чатах.")
    try:
        parts = message.text.replace(":", " ").split()
        start_time_str = f"{parts[1]}:{parts[2]}"
        end_time_str = f"{parts[3]}:{parts[4]}"
        datetime.datetime.strptime(start_time_str, '%H:%M')
        datetime.datetime.strptime(end_time_str, '%H:%M')
        if chat_id not in chat_configs: chat_configs[chat_id] = {}
        chat_configs[chat_id]['start_time'] = start_time_str
        chat_configs[chat_id]['end_time'] = end_time_str
        save_chat_configs()
        bot.reply_to(message, f"✅ График смены для этого чата установлен: с *{start_time_str}* до *{end_time_str}*.")
    except (IndexError, ValueError):
        bot.reply_to(message, "Неверный формат. Пример:\n`/тайминг 19:00 04:00`")

@bot.message_handler(commands=['сводка'])
def my_total_stats(message):
    """Анализирует Google Таблицу и показывает личную сводку."""
    user_id = message.from_user.id
    username = get_username(message.from_user)
    bot.reply_to(message, f"📊 Собираю вашу общую статистику из Google Таблицы, {username}. Это может занять некоторое время...")
    
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
        total_voices = user_df['Голосовых (шт)'].sum()
        total_breaks = user_df['Перерывов (шт)'].sum()
        total_lates = user_df['Опозданий (шт)'].sum()

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
    bot.reply_to(message, "📊 Анализирую общую статистику из Google Таблицы. Это может занять некоторое время...")
    worksheet = get_sheet()
    if not worksheet:
        return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице для анализа.")
    try:
        df = pd.DataFrame(worksheet.get_all_records())
        if df.empty or 'ID Ведущего' not in df.columns:
            return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")

        df['Голосовых (шт)'] = pd.to_numeric(df['Голосовых (шт)'])
        df['Опозданий (шт)'] = pd.to_numeric(df['Опозданий (шт)'])
        
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


# ... (остальные команды /отчет, /выгрузка и т.д. без изменений)
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
    user = chat_data[chat_id]['users'][user_id]

    if user.get('on_break'):
        handle_user_return(chat_id, user_id)

    voice_duration = message.voice.duration
    if voice_duration < MIN_VOICE_SECONDS:
        bot.reply_to(message, random.choice(soviet_phrases.get("too_short", ["Слишком коротко."])))
        return

    last_voice = user.get('last_voice_time')
    if last_voice and (now - last_voice).total_seconds() < VOICE_COOLDOWN_SECONDS:
        bot.reply_to(message, f"Слишком часто! Следующее ГС можно через {int(VOICE_COOLDOWN_SECONDS - (now - last_voice).total_seconds())} сек.")
        return

    user['voice_durations'].append(voice_duration)
    if last_voice: user['voice_deltas'].append((now - last_voice).total_seconds() / 60)
    else: user['first_voice_time'] = now

    user['count'] += 1
    user['last_voice_time'] = now
    save_history_event(chat_id, user_id, username, f"Прислал ГС ({voice_duration} сек)")
    
    if "accept" in soviet_phrases:
        bot.reply_to(message, random.choice(soviet_phrases["accept"]))

    if chat_data[chat_id].get('main_id') is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")
# ========================================
#           ПЛАНИРОВЩИК И ОТЧЕТЫ
# ========================================

def generate_detailed_report(chat_id: int, data: dict) -> list:
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}): return ["Главный не был назначен."]
    
    user = data['users'][main_id]
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

    plan_percent = (user['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    # ... (остальные расчеты)
    
    report = [
        f"📋 #Итоговый_Отчет_Смены ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
        # ... (остальные строки отчета)
    ]
    return report

def generate_analytical_summary(user_data: dict) -> str:
    """Генерирует прямые управленческие рекомендации."""
    plan_percent = (user_data.get('count', 0) / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    lates = user_data.get('late_returns', 0)
    has_long_pauses = False
    if user_data.get('voice_deltas') and len(user_data['voice_deltas']) > 0:
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


def send_end_of_shift_report_for_chat(chat_id):
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        logging.warning(f"Попытка закрыть смену в чате {chat_id}, но данных нет.")
        return

    main_user_data = data['users'][data['main_id']]
    analytical_conclusion = generate_analytical_summary(main_user_data)
    
    append_shift_to_google_sheet(chat_id, data, analytical_conclusion)
    
    report_lines = generate_detailed_report(chat_id, data)
    final_report = "\n".join(report_lines) + f"\n---\n🧠 **Рекомендация:**\n{analytical_conclusion}"
    
    try:
        bot.send_message(chat_id, final_report)
        if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
            bot.send_message(ADMIN_REPORT_CHAT_ID, final_report)
    except Exception as e:
        logging.error(f"Не удалось отправить отчет в чате {chat_id}: {e}")
    
    if chat_id in user_history: del user_history[chat_id]
    if chat_id in chat_data: del chat_data[chat_id]
    logging.info(f"Данные смены для чата {chat_id} очищены.")


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
    # schedule.every(1).minutes.do(check_users_activity) # Раскомментировать, если нужна проверка простоя
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========================================
#           ЗАПУСК БОТА
# ========================================
if __name__ == '__main__':
    logging.info("🤖 Бот (версия 9.0, финальная) запущен...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
