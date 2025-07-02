# utils.py
import json
import logging
import os
import datetime
import pytz
from telebot import types
from functools import wraps

# Импортируем переменные и данные из других модулей
from config import BOSS_ID, BREAK_DURATION_MINUTES
from state import chat_data, user_history

def load_json_data(filepath, default_value={}):
    """Загружает данные из JSON файла."""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки файла {filepath}: {e}")
    return default_value

def save_json_data(filepath, data):
    """Сохраняет данные в JSON файл."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения файла {filepath}: {e}")
        return False

def is_admin(bot, user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь админом чата."""
    if user_id == BOSS_ID:
        return True
    if chat_id > 0:
        return False  # В личных сообщениях нет админов
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    except Exception as e:
        logging.warning(f"Не удалось проверить права админа для user {user_id} в чате {chat_id}: {e}")
        return False

def admin_required(bot):
    """
    Декоратор для проверки прав администратора.
    Используется как @admin_required(bot).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(message):
            if not is_admin(bot, message.from_user.id, message.chat.id):
                return bot.reply_to(message, "⛔️ Эта команда доступна только администраторам чата.")
            return func(message)
        return wrapper
    return decorator

def get_username(user: types.User) -> str:
    """Возвращает форматированное имя пользователя."""
    return f"@{user.username}" if user.username else user.first_name

def get_chat_title(bot, chat_id: int) -> str:
    """Получает название чата по его ID."""
    try:
        return bot.get_chat(chat_id).title or str(chat_id)
    except Exception:
        return str(chat_id)

def init_user_data(user_id: int, username: str) -> dict:
    """Создает пустую структуру данных для нового пользователя."""
    return {
        'username': username, 'count': 0, 'on_break': False, 'breaks_count': 0,
        'late_returns': 0, 'last_voice_time': None, 'last_break_time': None,
        'break_start_time': None, 'voice_timeout_reminder_sent': False,
        'last_break_reminder_time': None, 'recognized_ads': [],
        'voice_deltas': [], 'voice_durations': []
    }

def init_shift_data(chat_id: int):
    """Создает пустую структуру данных для новой смены в чате."""
    from config import EXPECTED_VOICES_PER_SHIFT
    from state import chat_configs
    chat_data[chat_id] = {
        'main_id': None, 'users': {}, 'main_username': 'N/A',
        'shift_start': datetime.datetime.now(pytz.timezone('Europe/Moscow')),
        'shift_goal': chat_configs.get(chat_id, {}).get('default_goal', EXPECTED_VOICES_PER_SHIFT)
    }

def handle_user_return(bot, chat_id: int, user_id: int):
    """Обрабатывает возвращение пользователя с перерыва."""
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if not user or not user.get('on_break'):
        return

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
    """Сохраняет событие в лог истории смены."""
    if chat_id not in user_history:
        user_history[chat_id] = []
    now_str = datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    # Для наглядности можно добавить print или logging
    logging.info(f"HISTORY [{chat_id}]: {username} - {event_description}")
