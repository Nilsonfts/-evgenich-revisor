# -*- coding: utf-8 -*-
"""
Финальная версия с фиксированными перерывами и отслеживанием опозданий.
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
from functools import wraps

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
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

# Основные параметры
VOICE_TIMEOUT_MINUTES = 40
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
VOICE_COOLDOWN_SECONDS = 120 # 2 минуты
BREAK_DURATION_MINUTES = 15 # Фиксированная длительность перерыва
BREAK_DELAY_MINUTES = 60 # Нельзя брать перерыв чаще, чем раз в час

ADMIN_CHAT_ID = -1002645821302
shift_reports = []
user_history: Dict[int, List[str]] = {}

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

chat_data: Dict[int, dict] = {}

# ========================================
#           ДЕКОРАТОРЫ И ФУНКЦИИ
# ========================================

def admin_required(func):
    """Декоратор для проверки, что команду вызвал админ чата."""
    @wraps(func)
    def wrapper(message):
        try:
            user_id = message.from_user.id
            chat_id = message.chat.id
            if user_id == ADMIN_CHAT_ID: # Супер-админ может всегда
                return func(message)
            
            admins = [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
            if user_id in admins:
                return func(message)
            else:
                bot.reply_to(message, "⛔ Эту команду могут использовать только администраторы чата.")
        except Exception as e:
            logging.error(f"Ошибка проверки прав администратора: {e}")
            bot.reply_to(message, "Не удалось проверить ваши права администратора.")
    return wrapper

def get_username(user) -> str:
    """Получить username или имя пользователя."""
    if user.username:
        return f"@{user.username}"
    return user.first_name

def init_user_data(user_id, username):
    """Инициализация словаря для нового пользователя."""
    return {
        'username': username, 'count': 0, 'on_break': False,
        'breaks_count': 0, 'late_returns': 0, 'last_voice_time': None,
        'last_break_time': None, 'last_remind_time': None,
        'waiting_return_confirm': False, 'achievements': set(), 
        'voice_deltas': [], 'kudos': 0
    }

def handle_user_return(chat_id, user_id):
    """Общая логика для обработки возврата с перерыва."""
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if not user or not user.get('on_break'):
        return

    now = datetime.datetime.now(moscow_tz)
    break_duration_minutes = (now - user['break_start_time']).total_seconds() / 60
    
    user['on_break'] = False
    user['waiting_return_confirm'] = False # Сбрасываем флаг ожидания
    
    if break_duration_minutes > BREAK_DURATION_MINUTES:
        user['late_returns'] += 1
        bot.send_message(chat_id, f"✅ {user['username']}, с возвращением! Ты опоздал на {int(break_duration_minutes - BREAK_DURATION_MINUTES)} мин.")
        save_history_event(chat_id, user_id, user['username'], "Вернулся с перерыва с опозданием")
    else:
        bot.send_message(chat_id, f"👍 {user['username']}, с возвращением! Молодец, что вернулся вовремя.")
        save_history_event(chat_id, user_id, user['username'], "Вернулся с перерыва вовремя")

# ... остальные вспомогательные функции (get_chat_title, save_history_event и т.д.) ...
def get_chat_title(chat_id: int) -> str:
    try:
        title = bot.get_chat(chat_id).title
        return title if title else str(chat_id)
    except: return str(chat_id)

def save_history_event(chat_id, user_id, username, event_description):
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

def create_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    stats_button = types.InlineKeyboardButton("📊 Статистика", callback_data="get_stats")
    report_button = types.InlineKeyboardButton("📋 Финальный отчет", callback_data="get_report")
    help_button = types.InlineKeyboardButton("🆘 Помощь", callback_data="get_help")
    markup.add(stats_button, report_button, help_button)
    return markup
    
# ========================================
#           ОСНОВНЫЕ КОМАНДЫ И ОБРАБОТЧИКИ
# ========================================

@bot.message_handler(commands=['start', 'старт'])
def handle_start(message):
    # Эта функция теперь обрабатывает и /start, и передачу смены
    chat_id = message.chat.id
    if chat_id == ADMIN_CHAT_ID: return
    
    from_user = message.from_user
    username = get_username(from_user)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': datetime.datetime.now(moscow_tz), 'chat_title': get_chat_title(chat_id)}

    users = chat_data[chat_id]['users']
    if from_user.id not in users:
        users[from_user.id] = init_user_data(from_user.id, username)

    # Логика передачи смены
    match = re.match(r"/(start|старт)\s+@([a-zA-Z0-9_]+)", message.text.strip())
    if match:
        target_username = "@" + match.group(2)
        # Ищем пользователя среди всех, кто когда-либо писал в чате
        target_user_info = next((u for u in users.values() if u['username'] == target_username), None)
        if not target_user_info:
            bot.reply_to(message, f"Пользователь {target_username} не найден. Он должен сначала что-нибудь написать в чате.")
            return

        target_user_id = next((uid for uid, u in users.items() if u['username'] == target_username), None)

        markup = types.InlineKeyboardMarkup()
        accept_button = types.InlineKeyboardButton("✅ Принять смену", callback_data=f"accept_shift_{target_user_id}_{from_user.id}")
        decline_button = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_shift_{target_user_id}_{from_user.id}")
        markup.add(accept_button, decline_button)

        bot.send_message(chat_id, f"{target_username}, пользователь {username} предлагает вам принять смену. Ваш выбор?", reply_markup=markup)
        return

    # Если /start без параметров (назначаем себя главным)
    chat_data[chat_id]['main_id'] = from_user.id
    bot.send_message(chat_id, f"👑 {username}, вы назначены главным на смене! Удачи!", reply_markup=create_main_keyboard())
    save_history_event(chat_id, from_user.id, username, "Стал главным на смене")


@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in BREAK_KEYWORDS))
def handle_break_request(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_data.get(chat_id, {}).get('main_id') != user_id:
        bot.reply_to(message, "⛔ Перерыв может взять только главный на смене.")
        return
    user = chat_data[chat_id]['users'][user_id]

    if user.get('on_break'):
        bot.reply_to(message, "Вы уже на перерыве. Сначала вернитесь.")
        return
    
    last_break = user.get('last_break_time')
    if last_break and (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
        bot.reply_to(message, f"Вы недавно были на перерыве. Следующий можно взять через {int(BREAK_DELAY_MINUTES - (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60)} мин.")
        return

    user.update({
        'on_break': True,
        'break_start_time': datetime.datetime.now(moscow_tz),
        'last_break_time': datetime.datetime.now(moscow_tz),
        'breaks_count': user.get('breaks_count', 0) + 1
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат. Жду вашего возвращения.")
    save_history_event(chat_id, user_id, user['username'], f"Ушел на перерыв ({user['breaks_count']}-й раз)")


@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message.from_user)

    # Инициализация
    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': datetime.datetime.now(moscow_tz), 'chat_title': get_chat_title(chat_id)}
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)
    user = chat_data[chat_id]['users'][user_id]

    # Если на перерыве - возвращаем
    if user.get('on_break'):
        handle_user_return(chat_id, user_id)

    # ... (остальная логика: проверка длительности, анти-флуд, ритм и т.д.)
    now = datetime.datetime.now(moscow_tz)
    last_voice = user.get('last_voice_time')

    # Контроль Анти-флуд
    if last_voice and (now - last_voice).total_seconds() < VOICE_COOLDOWN_SECONDS:
        bot.reply_to(message, f"Слишком часто! Следующее голосовое будет засчитано в статистику через {int(VOICE_COOLDOWN_SECONDS - (now - last_voice).total_seconds())} сек.")
        save_history_event(chat_id, user_id, username, "Прислал голосовое (флуд)")
        return

    # Контроль ритма
    if last_voice:
        delta_minutes = (now - last_voice).total_seconds() / 60
        user['voice_deltas'].append(delta_minutes)

    user['count'] += 1
    user['last_voice_time'] = now
    
    # Если это первое гс, делаем юзера главным
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое голосовое!", reply_markup=create_main_keyboard())


@bot.message_handler(func=lambda m: m.text)
def handle_text_message(message):
    user_id = message.from_user.id
    # Если пользователь на перерыве и пишет, что вернулся
    if any(word in message.text.lower() for word in RETURN_CONFIRM_WORDS) and \
       chat_data.get(message.chat.id, {}).get('users', {}).get(user_id, {}).get('on_break'):
        handle_user_return(message.chat.id, user_id)


# ========================================
#           ПЛАНИРОВЩИК И ОТЧЕТЫ
# ========================================

def check_users_activity():
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id: continue
        user = data['users'][main_id]
        
        # Проверка возврата с перерыва
        if user.get('on_break') and not user.get('waiting_return_confirm'):
            minutes_on_break = (now - user['break_start_time']).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES:
                bot.send_message(chat_id, f"⏰ @{user['username']}, твой {BREAK_DURATION_MINUTES}-минутный перерыв закончился. Пора возвращаться!")
                user.update({'waiting_return_confirm': True})
        
        # ... (логика напоминаний об активности и т.д.)

def get_report_lines(chat_id, data):
    main_id = data.get('main_id')
    if not main_id: return ["Главный не назначен."]
    user = data['users'][main_id]
    
    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    
    return [
        f"📋 #Отчет_Текст_Ведущего ({data['shift_start'].strftime('%d.%m.%Y')})",
        f"🎤 Ведущий: {user['username']}",
        f"🗣️ Голосовых: {user['count']} из {EXPECTED_VOICES_PER_SHIFT}",
        f"☕ Перерывов: {user['breaks_count']}",
        f"⏳ Задержек после перерыва: {user['late_returns']}",
        f"👍 Благодарностей: {user['kudos']}",
        f"📈 Средний ритм: {avg_delta:.1f} мин/сообщение"
    ]

# ... (остальные функции отчетов, планировщика и запуска) ...
def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    # ...
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.info("🤖 Бот (версия с фикс. перерывами) запущен...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
