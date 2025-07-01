# -*- coding: utf-8 -*-
"""
Многофункциональный Telegram-бот для контроля смен, голосовых, перерывов, отчетов.
Финальная версия с геймификацией, кнопками, гибкой настройкой, полными банками фраз и уведомлениями для админа.
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
import re
import csv
from typing import Dict, Optional, List, Tuple
from telebot import types

# Импортируем фразы из отдельного файла
from phrases import (
    welcome_phrases, soviet_phrases, duty_call_phrases, duty_late_phrases,
    BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, ACHIEVEMENTS
)

# ========================================
#           НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения. Бот не может быть запущен.")

# Основные параметры смены (можно менять через /set)
SHIFT_START_HOUR = 19
SHIFT_END_HOUR = 4
VOICE_TIMEOUT_MINUTES = 40
REMIND_EACH_MINUTES = 5
BREAK_DURATION_MINUTES = 15
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
BREAK_DELAY_MINUTES = 60
WAIT_RETURN_CONFIRM_MINUTES = 3

ADMIN_CHAT_ID = -1002645821302
shift_reports = []
user_history: Dict[int, List[str]] = {}

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN)

chat_data: Dict[int, dict] = {}

# ========================================
#           ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def get_username(message) -> str:
    """Получить username или имя пользователя для сообщений."""
    if message.from_user.username:
        return f"@{message.from_user.username}"
    return message.from_user.first_name

def get_user_by_username(users_dict: dict, username: str) -> Tuple[Optional[int], Optional[dict]]:
    """Поиск пользователя по username в словаре пользователей чата."""
    for uid, info in users_dict.items():
        if info['username'].lower() == username.lower():
            return uid, info
    return None, None

def get_chat_title(chat_id: int) -> str:
    """Получение названия чата по его ID."""
    try:
        title = bot.get_chat(chat_id).title
        return title if title else str(chat_id)
    except Exception:
        return str(chat_id)

def break_requested(text: str) -> bool:
    """Проверяет, содержит ли текст ключевое слово для начала перерыва."""
    return any(word in text.lower() for word in BREAK_KEYWORDS)

def save_history_event(chat_id, user_id, username, event_description):
    """Сохраняет событие в истории смены для указанного чата."""
    if chat_id not in user_history:
        user_history[chat_id] = []
    now_str = datetime.datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

def create_main_keyboard():
    """Создает клавиатуру с основными командами."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    stats_button = types.InlineKeyboardButton("📊 Статистика", callback_data="get_stats")
    report_button = types.InlineKeyboardButton("📋 Финальный отчет", callback_data="get_report")
    help_button = types.InlineKeyboardButton("🆘 Помощь", callback_data="get_help")
    markup.add(stats_button, report_button, help_button)
    return markup

def check_and_award_achievements(chat_id, user_id, user_data):
    """Проверяет условия и выдает достижения в конце смены."""
    perc = round(user_data.get('count', 0) / EXPECTED_VOICES_PER_SHIFT * 100)
    
    if perc >= 100 and "perfect_shift" not in user_data["achievements"]:
        user_data["achievements"].add("perfect_shift")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, поздравляю! Ты получаешь достижение:\n_{ACHIEVEMENTS['perfect_shift']}_", parse_mode="Markdown")

    if perc >= 150 and "stakhanovets" not in user_data["achievements"]:
        user_data["achievements"].add("stakhanovets")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, вот это результат! Новое достижение:\n_{ACHIEVEMENTS['stakhanovets']}_", parse_mode="Markdown")

    if user_data.get('late_returns', 0) == 0 and "no_delays" not in user_data["achievements"]:
        user_data["achievements"].add("no_delays")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, отличная дисциплина! Достижение:\n_{ACHIEVEMENTS['no_delays']}_", parse_mode="Markdown")

def init_user_data(user_id, username):
    """Инициализация словаря для нового пользователя."""
    return {
        'username': username, 'count': 0, 'reminded': False, 'on_break': False,
        'breaks_count': 0, 'late_returns': 0, 'last_remind_time': None,
        'waiting_return_confirm': False, 'remind_return_time': None,
        'achievements': set()
    }

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ
# ========================================

@bot.message_handler(commands=["help"])
def show_help(message):
    HELP_TEXT = """<b>Справка по командам бота:</b>

/start — Назначить себя главным на смене.
/start @username — Назначить главным другого.
/restart или /рестарт — Перезапустить смену.

/статистика или /промежуточный — Промежуточный отчет по смене.
/рейтинг — Показать рейтинг по голосовым за текущую смену.
/моястатистика — Ваша личная статистика за эту смену.

/отчет — Сформировать финальный отчет по смене.
/выгрузка — Выгрузить лог событий смены в .txt файл.
/help — Показать эту справку."""
    bot.send_message(message.chat.id, HELP_TEXT, parse_mode="HTML")

@bot.message_handler(commands=["start", "старт"])
def send_welcome(message):
    """Обработчик команды /start: назначение главного."""
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    now = datetime.datetime.now(moscow_tz)
    user_id = message.from_user.id
    username = get_username(message)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': now, 'chat_title': get_chat_title(chat_id)}
        user_history[chat_id] = []

    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = init_user_data(user_id, username)
    
    chat_data[chat_id]['main_id'] = user_id
    chat_data[chat_id]['main_username'] = username
    chat_data[chat_id]['shift_start'] = now
    
    bot.reply_to(message, random.choice(welcome_phrases))
    bot.send_message(chat_id, f"{username}, теперь ты главный. Не забудь: голосовой — твоя обязанность!", reply_markup=create_main_keyboard())
    save_history_event(chat_id, user_id, username, "Стал главным на смене")

@bot.message_handler(commands=["restart", "рестарт"])
def restart_main(message):
    """Ручной перезапуск смены, сброс главного."""
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    if chat_id in chat_data:
        chat_data[chat_id]['main_id'] = None
        chat_data[chat_id]['main_username'] = None
        chat_data[chat_id]['shift_start'] = datetime.datetime.now(moscow_tz)
        bot.send_message(chat_id, "🔄 Смена перезапущена. Жду нового голосового для назначения главного!")
        save_history_event(message.chat.id, message.from_user.id, get_username(message), "Перезапустил смену")

@bot.message_handler(commands=["обед"])
def obed_command(message):
    """Команда /обед, эквивалент запроса на перерыв."""
    if message.chat.id == ADMIN_CHAT_ID: return
    handle_break_request(message)

@bot.message_handler(commands=["промежуточный", "статистика"])
def send_interim_report(message):
    """Команда для показа промежуточного отчёта/статистики."""
    chat_id = message.chat.id
    if chat_id not in chat_data:
        bot.send_message(chat_id, "Нет данных по смене в этом чате.")
        return
    report_lines = get_report_lines(chat_id, chat_data[chat_id])
    bot.send_message(chat_id, "\n".join(report_lines))

@bot.message_handler(commands=["отчет", "otchet"])
def send_manual_admin_report(message):
    """Ручная отправка финального отчёта."""
    send_end_of_shift_reports()
    send_admin_summary()
    bot.reply_to(message, "Отчёт по смене сформирован и отправлен.")
    save_history_event(message.chat.id, message.from_user.id, get_username(message), "Запросил финальный отчет")

@bot.message_handler(commands=['моястатистика'])
def my_stats(message):
    """Показывает личную статистику пользователя за текущую смену."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    if chat_id in chat_data and user_id in chat_data[chat_id]['users']:
        user_data = chat_data[chat_id]['users'][user_id]
        stats_text = (f"📊 Ваша статистика за текущую смену, {username}:\n"
                      f"🗣️ Голосовых: {user_data.get('count', 0)}\n"
                      f"☕ Перерывов: {user_data.get('breaks_count', 0)}\n"
                      f"⏳ Опозданий с перерыва: {user_data.get('late_returns', 0)}")
        bot.send_message(chat_id, stats_text)
    else:
        bot.send_message(chat_id, f"{username}, вашей статистики за текущую смену пока нет.")

@bot.message_handler(commands=['рейтинг'])
def show_rating(message):
    """Показывает рейтинг пользователей по количеству голосовых за смену."""
    chat_id = message.chat.id
    if chat_id in chat_data and chat_data[chat_id]['users']:
        users = chat_data[chat_id]['users']
        sorted_users = sorted(users.items(), key=lambda item: item[1]['count'], reverse=True)
        
        rating_text = "🏆 Рейтинг по голосовым за текущую смену:\n\n"
        for i, (uid, udata) in enumerate(sorted_users[:10], 1):
            rating_text += f"{i}. {udata['username']} — {udata['count']} голосовых\n"
        bot.send_message(chat_id, rating_text)
    else:
        bot.send_message(chat_id, "Пока нечего показывать в рейтинге.")

@bot.message_handler(commands=['set'], chat_id=[ADMIN_CHAT_ID])
def set_config(message):
    """Команда для админа для изменения настроек на лету."""
    global EXPECTED_VOICES_PER_SHIFT, VOICE_TIMEOUT_MINUTES
    try:
        parts = message.text.split()
        if len(parts) != 3:
            raise ValueError("Неверный формат команды")
        
        _, param, value = parts
        value = int(value)
        
        if param.lower() == 'voices':
            EXPECTED_VOICES_PER_SHIFT = value
            bot.reply_to(message, f"✅ Новая норма голосовых: {value}")
        elif param.lower() == 'timeout':
            VOICE_TIMEOUT_MINUTES = value
            bot.reply_to(message, f"✅ Новый таймаут для напоминаний: {value} минут")
        else:
            bot.reply_to(message, "Неизвестный параметр. Доступно: voices, timeout")
    except Exception as e:
        bot.reply_to(message, f"Ошибка. Формат: /set <параметр> <значение>\nПример: /set voices 20\nДетали: {e}")

# ========================================
#       ОБРАБОТКА СООБЩЕНИЙ И КНОПОК
# ========================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Обрабатывает нажатия на inline-кнопки."""
    try:
        bot.answer_callback_query(callback_query_id=call.id)
        if call.data == "get_stats":
            send_interim_report(call.message)
        elif call.data == "get_report":
            send_manual_admin_report(call.message)
        elif call.data == "get_help":
            show_help(call.message)
    except Exception as e:
        logging.error(f"Ошибка в обработчике кнопок: {e}")

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    """Обработка голосовых сообщений: учёт, назначение главного, сброс напоминаний."""
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': now, 'chat_title': get_chat_title(chat_id)}
    
    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = init_user_data(user_id, username)

    user = users[user_id]
    voice_duration = message.voice.duration
    save_history_event(chat_id, user_id, username, f"Прислал голосовое ({voice_duration} сек)")

    if voice_duration < MIN_VOICE_SECONDS:
        bot.send_message(chat_id, random.choice(soviet_phrases["too_short"]))
        return

    user['count'] += 1
    user['last_voice_time'] = now
    user['reminded'] = False
    
    if chat_data[chat_id].get('duty_check_time'):
        if now - chat_data[chat_id]['duty_check_time'] < datetime.timedelta(minutes=31):
            chat_data[chat_id]['duty_confirmed'] = True

    if user.get('waiting_return_confirm'):
        user['on_break'] = False
        user['waiting_return_confirm'] = False
        bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
        if (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
            user['late_returns'] += 1
            save_history_event(chat_id, user_id, username, "Вернулся с перерыва с опозданием (голос)")
        else:
            save_history_event(chat_id, user_id, username, "Вернулся с перерыва вовремя (голос)")

    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        text = f"{username}, теперь ты главный. Не забудь: голосовой — твоя обязанность!"
        bot.send_message(chat_id, text, reply_markup=create_main_keyboard())
        save_history_event(chat_id, user_id, username, "Стал главным (первое голосовое)")
    elif chat_data[chat_id]['main_id'] == user_id:
        bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['accept'])}")

@bot.message_handler(func=lambda m: m.text and break_requested(m.text))
def handle_break_request(message):
    """Обработчик запросов на перерыв по ключевым словам."""
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)

    if chat_id not in chat_data or chat_data[chat_id].get('main_id') != user_id:
        bot.reply_to(message, "⛔ Перерыв может взять только текущий главный на смене.")
        return

    user = chat_data[chat_id]['users'][user_id]
    last_break_time = user.get('last_break_time')
    if last_break_time and (now - last_break_time).total_seconds() / 60 < BREAK_DELAY_MINUTES:
        remaining = int(BREAK_DELAY_MINUTES - (now - last_break_time).total_seconds() / 60)
        bot.reply_to(message, random.choice(soviet_phrases["break_too_soon"]).format(minutes=remaining))
        return

    user.update({
        'breaks_count': user.get('breaks_count', 0) + 1, 'on_break': True,
        'break_start_time': now, 'last_break_time': now, 'waiting_return_confirm': False,
    })
    bot.reply_to(message, random.choice(soviet_phrases["break_acknowledgement"]).format(username=username))
    save_history_event(chat_id, user_id, username, f"Ушел на перерыв ({user['breaks_count']}-й раз)")

@bot.message_handler(func=lambda m: m.text)
def handle_text_message(message):
    """Обработка текстовых сообщений для подтверждения возврата с перерыва."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)

    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if user and user.get('waiting_return_confirm'):
        if any(word in message.text.lower() for word in RETURN_CONFIRM_WORDS):
            user['on_break'] = False
            user['waiting_return_confirm'] = False
            bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
            if (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                user['late_returns'] += 1
                save_history_event(chat_id, user_id, username, "Вернулся с перерыва с опозданием (текст)")
            else:
                save_history_event(chat_id, user_id, username, "Вернулся с перерыва вовремя (текст)")

# ========================================
#           ОТЧЁТЫ И СТАТИСТИКА
# ========================================

def get_report_lines(chat_id, data, full_report=False):
    """Генерация текста для отчёта."""
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}):
        return ["Главный ведущий ещё не назначен."]
    
    main_user = data['users'][main_id]
    said_count = main_user.get('count', 0)
    perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100)
    
    tag = "#Отчет_Текст_Ведущего" if full_report else "#Промежуточный_отчет"
    report_lines = [
        f"📋 {tag} ({data.get('shift_start', datetime.datetime.now(moscow_tz)).strftime('%d.%m.%Y')})",
        f"🏢 Чат: {data.get('chat_title') or get_chat_title(chat_id)}",
        f"🎤 Ведущий: {main_user.get('username', 'Неизвестно')}",
        f"🗣️ Голосовых: {said_count} из {EXPECTED_VOICES_PER_SHIFT} ({perc}%)",
        f"☕ Перерывов: {main_user.get('breaks_count', 0)}",
        f"⏳ Задержек после перерыва: {main_user.get('late_returns', 0)}",
    ]
    if full_report:
        if perc >= 100: praise = "\n" + random.choice(soviet_phrases["praise"])
        elif perc < 50: praise = "\n⚠️ Смена провалена, эфир был слишком тихим!"
        else: praise = ""
        report_lines.append(praise)
    return report_lines

def send_end_of_shift_reports():
    """Отправка финальных отчётов и выдача достижений."""
    global shift_reports
    shift_reports = []
    
    for chat_id, data in chat_data.items():
        main_id = data.get('main_id')
        if not main_id: continue
        
        main_user_data = data['users'][main_id]
        check_and_award_achievements(chat_id, main_id, main_user_data)
        
        report_text_list = get_report_lines(chat_id, data, full_report=True)
        final_report = "\n".join(filter(None, report_text_list))
        
        try:
            bot.send_message(chat_id, final_report)
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат {chat_id}: {e}")
            
        shift_reports.append({
            "chat_id": chat_id, "chat_title": data.get('chat_title'), "report": final_report
        })
    chat_data.clear()
    user_history.clear()

def send_admin_summary():
    """Отправка сводного отчёта для руководства."""
    if not shift_reports: return
    
    def get_official_conclusion(perc):
        if perc >= 150: return "План перевыполнен, выдающаяся работа!"
        if perc >= 100: return "План выполнен полностью."
        if perc >= 80: return "План выполнен частично, сотрудник проявил инициативу."
        if perc >= 50: return "План не выполнен, требуется улучшение дисциплины."
        return "План провален, требуется строгий контроль."
    
    intro = random.choice(["@nilfts Я все про них знаю! 🕵️‍♂️ Вот как они отработали:", "@nilfts Всё под контролем! Вот свежий отчёт по смене:"])
    report_lines = [intro, ""]
    
    for item in shift_reports:
        lines = item["report"].splitlines()
        said_count = 0
        try:
            said_line = next(line for line in lines if "Всего голосовых" in line)
            said_count = int(re.search(r'(\d+)\s*из', said_line).group(1))
        except (StopIteration, AttributeError): pass
        
        perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0
        conclusion = get_official_conclusion(perc)
        
        report_lines.append(f"<b>🏢 Чат: {item.get('chat_title', 'Неизвестный чат')}</b>")
        report_lines.append(item["report"])
        report_lines.append(f"<i>{conclusion}</i>")
        report_lines.append("-" * 20)
        
    try:
        bot.send_message(ADMIN_CHAT_ID, "\n".join(report_lines), parse_mode="HTML")
    except Exception as e:
        logging.error(f"Не удалось отправить админ-отчет: {e}")
    shift_reports.clear()

# ========================================
#           ПЛАНИРОВЩИК ЗАДАЧ
# ========================================

def check_users_activity():
    """Проверка активности, напоминания, отслеживание перерывов."""
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id or main_id not in data.get('users', {}): continue
        user = data['users'][main_id]
        username = user['username']
        
        if user.get('on_break'):
            minutes_on_break = (now - user['break_start_time']).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES and not user.get('waiting_return_confirm'):
                bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['return_demand'])}")
                user.update({'waiting_return_confirm': True, 'remind_return_time': now})
                save_history_event(chat_id, main_id, username, "Отправлено напоминание о возврате с перерыва")
            continue

        if user.get('waiting_return_confirm'):
            remind_time = user.get('remind_return_time')
            if remind_time and (now - remind_time).total_seconds() / 60 > WAIT_RETURN_CONFIRM_MINUTES:
                bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['return_demand_hard'])}")
                user['remind_return_time'] = now
            continue

        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES:
                last_remind = user.get('last_remind_time')
                if not last_remind or (now - last_remind).total_seconds() / 60 >= REMIND_EACH_MINUTES:
                    bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['scary_reminder'])}")
                    user['last_remind_time'] = now
                    save_history_event(chat_id, main_id, username, "Отправлено напоминание о голосовом")
                    if minutes_passed > VOICE_TIMEOUT_MINUTES * 1.5:
                         bot.send_message(ADMIN_CHAT_ID, f"⚠️ Алярм! В чате '{get_chat_title(chat_id)}' ведущий {username} молчит уже {int(minutes_passed)} минут!")

def duty_check_reminder():
    """Напоминание о начале смены, если главный не назначен."""
    now = datetime.datetime.now(moscow_tz)
    for chat_id in chat_data:
        if chat_id != ADMIN_CHAT_ID and not chat_data[chat_id].get('main_id'):
            bot.send_message(chat_id, random.choice(duty_call_phrases))
            chat_data[chat_id].update({'duty_check_time': now, 'duty_confirmed': False})

def duty_check_late():
    """Проверка, что главный назначен вовремя."""
    for chat_id, data in chat_data.items():
        if data.get('duty_check_time') and not data.get('duty_confirmed'):
            bot.send_message(chat_id, random.choice(duty_late_phrases))
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ Внимание! Смена в чате '{get_chat_title(chat_id)}' не началась вовремя.")
            data.update({'duty_check_time': None, 'duty_confirmed': False})

def run_scheduler():
    """Запуск всех запланированных задач."""
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("04:01", moscow_tz).do(send_end_of_shift_reports)
    schedule.every().day.at("09:00", moscow_tz).do(send_admin_summary)
    schedule.every().day.at("19:00", moscow_tz).do(duty_check_reminder)
    schedule.every().day.at("19:31", moscow_tz).do(duty_check_late)
    
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")
        time.sleep(1)

# ========================================
#                ЗАПУСК БОТА
# ========================================

if __name__ == '__main__':
    logging.info("🤖 Бот запущен...")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
