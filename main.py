# -*- coding: utf-8 -*-
"""
Финальная версия бота v5.1:
- Добавлена команда /testsheet для проверки соединения с Google.
- Все предыдущие функции сохранены.
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

# Импорт gspread для работы с Google Таблицами
try:
    import gspread
except ImportError:
    logging.error("Библиотека gspread не найдена. Установите ее: pip install gspread google-auth-oauthlib")
    gspread = None

# Импорт фраз
try:
    from phrases import soviet_phrases, BREAK_KEYWORDS, RETURN_CONFIRM_WORDS
except ImportError:
    logging.warning("Файл 'phrases.py' не найден. Используются значения по умолчанию.")
    BREAK_KEYWORDS = ["перерыв", "отдых"]
    RETURN_CONFIRM_WORDS = ["вернулся", "на месте"]
    soviet_phrases = {"too_short": ["Слишком коротко!"], "accept": ["Принято."]}

# ========================================
#           НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

BOSS_ID = 196614680
ADMIN_REPORT_CHAT_ID = -1002645821302 
LAST_REPORT_FILE = 'last_shift_report.txt'

# Параметры смены
VOICE_TIMEOUT_MINUTES = 40
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False, parse_mode="Markdown")
chat_data: Dict[int, dict] = {}
user_history: Dict[int, List[str]] = {}

# ========================================
#      РАБОТА С GOOGLE ТАБЛИЦАМИ
# ========================================
def get_sheet():
    """Авторизуется и возвращает рабочий лист Google Таблицы по ключу."""
    if not gspread: return None
    try:
        creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
        sheet_key = os.getenv("GOOGLE_SHEET_KEY")
        if not creds_json_str or not sheet_key:
            logging.error("Переменные окружения для Google Sheets не найдены!")
            return None
        
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        spreadsheet = gc.open_by_key(sheet_key)
        return spreadsheet.sheet1
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error(f"Таблица с ключом не найдена. Проверьте ID и права доступа для сервисного аккаунта.")
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
                "Опозданий (шт)", "Средний ритм (мин)", "Макс. пауза (мин)", "Ср. длина ГС (сек)"
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:M1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
            logging.info("Создана шапка в Google Таблице.")
    except Exception as e:
        logging.error(f"Не удалось создать шапку в Google Таблице: {e}")

def append_shift_to_google_sheet(chat_id, data):
    """Добавляет строку с итогами смены в Google Таблицу."""
    worksheet = get_sheet()
    if not worksheet:
        logging.error("Выгрузка в Google Sheets невозможна: лист не найден.")
        return

    create_sheet_header_if_needed(worksheet)
    
    main_id = data.get('main_id')
    user_data = data.get('users', {}).get(main_id)
    if not user_data: return
    
    now = datetime.datetime.now(moscow_tz)
    plan_percent = (user_data['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    avg_delta = sum(user_data['voice_deltas']) / len(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    max_pause = max(user_data['voice_deltas']) if user_data['voice_deltas'] else 0
    avg_duration = sum(user_data['voice_durations']) / len(user_data['voice_durations']) if user_data['voice_durations'] else 0

    row_data = [
        data.get('shift_start', now).strftime('%d.%m.%Y'),
        chat_id, get_chat_title(chat_id),
        main_id, user_data['username'],
        user_data['count'], EXPECTED_VOICES_PER_SHIFT, f"{plan_percent:.0f}%",
        user_data['breaks_count'], user_data['late_returns'],
        f"{avg_delta:.1f}", f"{max_pause:.1f}", f"{avg_duration:.1f}",
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
    except Exception as e:
        logging.error(f"Ошибка проверки администратора в чате {chat_id}: {e}")
        return False

def admin_required(func):
    @wraps(func)
    def wrapper(message):
        chat_id_for_check = message.chat.id if message.chat.type != 'private' else ADMIN_REPORT_CHAT_ID
        if not is_admin(message.from_user.id, chat_id_for_check):
            bot.reply_to(message, "⛔ Эту команду могут использовать только администраторы.")
            return
        return func(message)
    return wrapper

def get_username(user) -> str:
    return f"@{user.username}" if user.username else user.first_name

def init_user_data(user_id, username):
    return {
        'username': username, 'count': 0, 'on_break': False, 'breaks_count': 0,
        'late_returns': 0, 'last_voice_time': None, 'last_break_time': None,
        'reminder_sent_at': None, 'response_times': [], 'voice_deltas': [], 'voice_durations': [],
        'break_start_time': None
    }

def handle_user_return(chat_id, user_id):
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if not user or not user.get('on_break'): return

    now = datetime.datetime.now(moscow_tz)
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
    except Exception:
        return str(chat_id)

def save_history_event(chat_id, user_id, username, event_description):
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ
# ========================================
@bot.message_handler(commands=['start', 'старт'])
def handle_start(message):
    chat_id = message.chat.id
    if chat_id > 0:
        bot.reply_to(message, "Эта команда работает только в групповом чате.")
        return

    from_user = message.from_user
    username = get_username(from_user)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': datetime.datetime.now(moscow_tz)}

    if from_user.id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][from_user.id] = init_user_data(from_user.id, username)

    try:
        target_username = message.text.split()[1]
        if target_username.startswith('@'):
            all_users_in_chat = chat_data[chat_id].get('users', {})
            target_user_info = next((u for u in all_users_in_chat.values() if u['username'].lower() == target_username.lower()), None)
            
            if not target_user_info:
                bot.reply_to(message, f"Пользователь {target_username} не найден. Он должен сначала что-нибудь написать в этом чате.")
                return
            
            target_user_id = next(uid for uid, u in all_users_in_chat.items() if u['username'].lower() == target_username.lower())
            
            chat_data[chat_id]['main_id'] = target_user_id
            chat_data[chat_id]['main_username'] = target_user_info['username']
            bot.send_message(chat_id, f"👑 По команде от {username}, новым главным на смене назначен {target_user_info['username']}!")
            save_history_event(chat_id, from_user.id, username, f"Передал смену {target_user_info['username']}")
            return
    except IndexError:
        pass

    if chat_data[chat_id].get('main_id') is not None:
        main_username = chat_data[chat_id].get('main_username', 'Неизвестно')
        bot.reply_to(message, f"Смена уже занята. Текущий главный: {main_username}.")
        return

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


@bot.message_handler(commands=['check', 'промежуточный', 'статистика'])
@admin_required
def admin_check_shift(message):
    if message.chat.type == 'private' and message.from_user.id == BOSS_ID:
        chat_id = ADMIN_REPORT_CHAT_ID
    else:
        chat_id = message.chat.id
        
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        bot.reply_to(message, f"В чате `{get_chat_title(chat_id)}` смена еще не началась.")
        return

    user = data.get('users', {}).get(data['main_id'])
    if not user:
        bot.reply_to(message, "Не найдены данные по текущему ведущему.")
        return

    plan_percent = (user['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
    report_text = (
        f"📋 #Промежуточный_отчет ({datetime.datetime.now(moscow_tz).strftime('%d.%m.%Y')})\n"
        f"🏢 Чат: {get_chat_title(chat_id)}\n"
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
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        bot.reply_to(message, "Смена еще не началась, финальный отчет невозможен.")
        return

    report_lines = generate_detailed_report(chat_id, data)
    analytical_summary = generate_analytical_summary(data['users'][data['main_id']])
    final_report = "\n".join(report_lines) + "\n" + analytical_summary
    
    bot.send_message(chat_id, final_report)
    if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
        bot.send_message(ADMIN_REPORT_CHAT_ID, final_report)


@bot.message_handler(commands=['выгрузка'])
@admin_required
def admin_export_history(message):
    chat_id = message.chat.id
    history = user_history.get(chat_id)

    if not history:
        bot.reply_to(message, "История событий для этого чата пуста.")
        return

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


@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = """
*Справка по командам бота:*

`/start` — Назначить себя главным на смене.
`/start @username` — Назначить другого пользователя главным по его тегу.
`/restart` или `/рестарт` — Перезапустить смену, сбросив текущего главного.

`/промежуточный` — Показать промежуточный отчет по активности.
`/статистика` — Показать текущую статистику (аналог промежуточного отчета).
`/отчет` — Сформировать и отправить финальный отчет по смене в чат и руководству.

`/обед` или `/перерыв` — Уйти на перерыв (только для главного).
`/выгрузка` — Выгрузить историю всех событий смены в виде файла.

`/analyze` или `/весьотчет` — (Только для админов) Показать рейтинг всех сотрудников.
`/testsheet` — (Только для админов) Проверить соединение с Google Sheets.
`/help` — Показать эту справку.

*Ключевые слова:*
- Для ухода на перерыв можно написать: `перерыв`, `обед`, `покурить`, `отойду` и т.д.
- Для возврата с перерыва: `на месте`, `вернулся`, `пришел`, `тут` и т.д.
"""
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['testsheet'])
@admin_required
def test_google_sheet(message):
    """(Только для админов) Тестирует соединение с Google Sheets."""
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
            f"Не удалось подключиться к Google Sheets. Проверьте лог бота в консоли для подробной информации.\n\n"
            f"**Частые причины:**\n"
            f"1. Неверный ID таблицы в переменной `GOOGLE_SHEET_KEY`.\n"
            f"2. Ошибка в данных ключа `GOOGLE_CREDENTIALS_JSON`.\n"
            f"3. Вы не предоставили доступ сервисному аккаунту (`evgenich-logger@...`) к вашей таблице с правами 'Редактора'."
        )

# ========================================
#           ОБРАБОТЧИКИ СООБЩЕНИЙ
# ========================================
@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
    if chat_id > 0: return

    user_id = message.from_user.id
    username = get_username(message.from_user)
    now = datetime.datetime.now(moscow_tz)

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

@bot.message_handler(commands=['перерыв', 'обед'])
def handle_break_command(message):
    handle_break_request(message)

@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in BREAK_KEYWORDS))
def handle_break_request(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_id > 0: return

    if chat_data.get(chat_id, {}).get('main_id') != user_id: return
        
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id, {})
    if user.get('on_break'):
        bot.reply_to(message, "Вы уже на перерыве.")
        return

    last_break = user.get('last_break_time')
    if last_break and (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
        remaining_time = int(BREAK_DELAY_MINUTES - (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60)
        bot.reply_to(message, f"Следующий перерыв можно взять через {remaining_time} мин.")
        return

    user.update({
        'on_break': True, 'break_start_time': datetime.datetime.now(moscow_tz),
        'last_break_time': datetime.datetime.now(moscow_tz),
        'breaks_count': user.get('breaks_count', 0) + 1,
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
    save_history_event(chat_id, user_id, get_username(message.from_user), "Ушел на перерыв")
    
@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in RETURN_CONFIRM_WORDS))
def handle_return_message(message):
    user_id = message.from_user.id
    if message.chat.id > 0: return
    if chat_data.get(message.chat.id, {}).get('main_id') == user_id:
        handle_user_return(message.chat.id, user_id)

# ========================================
#           ПЛАНИРОВЩИК И ОТЧЕТЫ
# ========================================
def check_users_activity():
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id or not data.get('users', {}).get(main_id): continue
        user = data['users'][main_id]
        username = user.get('username', 'Ведущий')

        if user.get('on_break') and not user.get('pre_return_warning_sent', False):
            if user.get('break_start_time') and (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                reminder_text = random.choice(soviet_phrases.get("return_demand", ["пора возвращаться."]))
                bot.send_message(chat_id, f"⏰ {username}, {reminder_text}")
                user['pre_return_warning_sent'] = True
        
        last_voice = user.get('last_voice_time')
        if not user.get('on_break') and last_voice and not user.get('reminder_sent_at'):
            if (now - last_voice).total_seconds() / 60 > VOICE_TIMEOUT_MINUTES:
                reminder_text = random.choice(soviet_phrases.get("voice_reminder", ["вы давно не выходили в эфир."]))
                bot.send_message(chat_id, f"🚨 {username}, {reminder_text}")
                user['reminder_sent_at'] = now
                save_history_event(chat_id, main_id, username, "Отправлено напоминание о простое")

def generate_detailed_report(chat_id: int, data: dict) -> list:
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}): return ["Главный не был назначен."]
    
    user = data['users'][main_id]
    now = datetime.datetime.now(moscow_tz)

    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    short_voices_perc = (sum(1 for d in user['voice_durations'] if d < 10) / len(user['voice_durations']) * 100) if user['voice_durations'] else 0
    avg_response_time = sum(user.get('response_times', [])) / len(user.get('response_times', [])) if user.get('response_times') else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
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
        f"⚡️ Реакция на напом.: {avg_response_time:.1f} мин." if avg_response_time else "⚡️ Напоминаний не было", "---",
        "**Качество (косвенно):**",
        f"📏 Ср. длина ГС: {avg_duration:.1f} сек.",
        f"🤏 Коротких ГС (<10с): {short_voices_perc:.0f}%"
    ]
    return report

def generate_analytical_summary(user_data: dict) -> str:
    summary = ["\n---", "🧠 **Анализ смены:**"]
    
    if user_data.get('voice_deltas') and len(user_data['voice_deltas']) > 0:
        if max(user_data['voice_deltas']) > VOICE_TIMEOUT_MINUTES * 1.5:
            summary.append("•  зона роста: были длинные паузы в эфире.")
        else:
            summary.append("• сильная сторона: хороший, стабильный ритм.")

    if user_data.get('response_times'):
        if (sum(user_data['response_times']) / len(user_data['response_times'])) < 3:
            summary.append("• сильная сторона: отличная реакция на напоминания.")
        else:
            summary.append("• зона роста: стоит быстрее реагировать на уведомления.")
            
    if user_data.get('late_returns', 0) > 0:
        summary.append(f"• зона роста: зафиксировано {user_data['late_returns']} опоздание(й).")
    
    return "\n".join(summary) if len(summary) > 2 else "\nОтличная работа, замечаний нет!"

def send_end_of_shift_reports():
    logging.info("Начало отправки итоговых отчетов по сменам в 04:01...")
    active_chats_copy = list(chat_data.keys())

    for chat_id in active_chats_copy:
        data = chat_data.get(chat_id)
        if not data or not data.get('main_id') or data['main_id'] not in data.get('users', {}):
            continue
        
        main_user_data = data['users'][data['main_id']]
        if main_user_data.get('count', 0) > 0:
            append_shift_to_google_sheet(chat_id, data)
            
            report_lines = generate_detailed_report(chat_id, data)
            analytical_summary = generate_analytical_summary(main_user_data)
            final_report = "\n".join(report_lines) + "\n" + analytical_summary
            
            try:
                bot.send_message(chat_id, final_report)
                if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
                    bot.send_message(ADMIN_REPORT_CHAT_ID, final_report)
                with open(LAST_REPORT_FILE, 'w', encoding='utf-8') as f:
                    f.write(final_report)
            except Exception as e:
                logging.error(f"Не удалось отправить/сохранить отчет в чате {chat_id}: {e}")
    
    chat_data.clear()
    user_history.clear()
    logging.info("Данные всех смен очищены.")

def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("04:01", "Europe/Moscow").do(send_end_of_shift_reports)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========================================
#           ЗАПУСК БОТА
# ========================================
if __name__ == '__main__':
    logging.info("🤖 Бот (версия 5.1, Google Sheets по ID) запущен...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
