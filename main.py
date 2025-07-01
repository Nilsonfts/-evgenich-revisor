# -*- coding: utf-8 -*-
"""
Каноничная финальная версия бота, включающая все реализованные механики:
- Продвинутый контроль и отчетность
- HR-функции (тренировка, анализ)
- Умное контекстное меню для всех ролей
- Система "БОССА" и права администраторов
- Передача смены и обработка опозданий
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
from telebot import types
from functools import wraps
from typing import Dict, List, Optional
# Попытка импортировать фразы, если файла нет - используются заглушки
try:
    from phrases import (
        welcome_phrases, soviet_phrases,
        BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, ACHIEVEMENTS
    )
except ImportError:
    logging.warning("Файл 'phrases.py' не найден. Используются значения по умолчанию.")
    BREAK_KEYWORDS = ["перерыв", "отдых"]
    RETURN_CONFIRM_WORDS = ["вернулся", "на месте"]
    soviet_phrases = {"too_short": ["Слишком коротко!"], "accept": ["Принято."]}


# ========================================
#           НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

# Убедитесь, что BOT_TOKEN задан в переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения. Задайте его перед запуском.")

# ID суперпользователя (БОСС) и чата для админских отчетов
BOSS_ID = 196614680
ADMIN_REPORT_CHAT_ID = -1002645821302 # Пример ID, замените на свой

# Параметры смены
VOICE_TIMEOUT_MINUTES = 40
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
chat_data: Dict[int, dict] = {}
user_history: Dict[int, list] = {}

# ========================================
#           ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================
def is_admin(user_id, chat_id):
    """Проверяет, является ли пользователь администратором или БОССОМ."""
    if user_id == BOSS_ID: return True
    try:
        admin_ids = [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
        return user_id in admin_ids
    except Exception as e:
        logging.error(f"Ошибка проверки администратора в чате {chat_id}: {e}")
        return False

def admin_required(func):
    """Декоратор для команд, доступных только администраторам."""
    @wraps(func)
    def wrapper(message):
        if not is_admin(message.from_user.id, message.chat.id):
            bot.reply_to(message, "⛔ Эту команду могут использовать только администраторы чата.")
            return
        return func(message)
    return wrapper

def get_username(user) -> str:
    """Получает @username или имя пользователя."""
    return f"@{user.username}" if user.username else user.first_name

def init_user_data(user_id, username):
    """Инициализирует словарь для нового пользователя."""
    return {
        'username': username, 'count': 0, 'on_break': False, 'breaks_count': 0,
        'late_returns': 0, 'last_voice_time': None, 'last_break_time': None,
        'pre_return_warning_sent': False, 'reminder_sent_at': None, 'response_times': [],
        'achievements': set(), 'voice_deltas': [], 'voice_durations': [], 'kudos': 0,
        'in_training': False, 'first_voice_time': None, 'waiting_return_confirm': False,
        'break_start_time': None
    }

def handle_user_return(chat_id, user_id):
    """Обрабатывает возврат пользователя с перерыва."""
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if not user or not user.get('on_break'): return

    now = datetime.datetime.now(moscow_tz)
    break_duration_minutes = (now - user['break_start_time']).total_seconds() / 60

    user['on_break'] = False
    user['waiting_return_confirm'] = False

    if break_duration_minutes > BREAK_DURATION_MINUTES:
        user['late_returns'] += 1
        bot.send_message(chat_id, f"✅ {user['username']}, с возвращением! Вы опоздали на {int(break_duration_minutes - BREAK_DURATION_MINUTES)} мин.")
    else:
        bot.send_message(chat_id, f"👍 {user['username']}, с возвращением! Молодец, что вернулись вовремя.")

    save_history_event(chat_id, user_id, user['username'], f"Вернулся с перерыва (длительность {break_duration_minutes:.1f} мин)")
    fake_message = types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), from_user=types.SimpleNamespace(id=user_id))
    show_menu(fake_message)

def get_chat_title(chat_id: int) -> str:
    """Получает название чата по его ID."""
    try:
        title = bot.get_chat(chat_id).title
        return title if title else str(chat_id)
    except Exception:
        return str(chat_id)

def save_history_event(chat_id, user_id, username, event_description):
    """Сохраняет событие в историю для последующего аудита."""
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")


# ========================================
#           КЛАВИАТУРЫ И НАВИГАЦИЯ
# ========================================
def create_contextual_keyboard(chat_id, user_id):
    """Создает контекстную клавиатуру в зависимости от роли и статуса пользователя."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, row_width=2)
    current_main_id = chat_data.get(chat_id, {}).get('main_id')
    user_data = chat_data.get(chat_id, {}).get('users', {}).get(user_id, {})

    if current_main_id is None:
        markup.add(types.KeyboardButton("🚀 Встать в смену"))

    if current_main_id == user_id:
        if user_data.get('on_break'):
            markup.add(types.KeyboardButton("✅ Я вернулся"))
        else:
            markup.add(types.KeyboardButton("☕️ Уйти на перерыв"))

    markup.add(types.KeyboardButton("ℹ️ Сводка по смене"), types.KeyboardButton("⭐️ Моя статистика"))

    if is_admin(user_id, chat_id):
        markup.add(types.KeyboardButton("🚨 Отчет по прогульщикам"), types.KeyboardButton("🕵️ Аудит смены"))

    markup.add(types.KeyboardButton("🆘 Помощь"), types.KeyboardButton("Скрыть меню"))
    return markup

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ И ОБРАБОТЧИКИ
# ========================================
@bot.message_handler(commands=['start', 'старт'])
def handle_start(message):
    """Обрабатывает заступление на смену."""
    chat_id = message.chat.id
    from_user = message.from_user
    username = get_username(from_user)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': datetime.datetime.now(moscow_tz), 'chat_title': get_chat_title(chat_id)}

    users = chat_data[chat_id]['users']
    if from_user.id not in users:
        users[from_user.id] = init_user_data(from_user.id, username)

    if chat_data[chat_id].get('main_id') is not None:
        main_username = chat_data[chat_id].get('main_username', 'Неизвестно')
        bot.reply_to(message, f"Смена уже занята. Текущий главный: {main_username}.")
        return

    chat_data[chat_id]['main_id'] = from_user.id
    chat_data[chat_id]['main_username'] = username
    bot.send_message(chat_id, f"👑 {username}, вы заступили на смену! Удачи!")
    save_history_event(chat_id, from_user.id, username, "Стал главным на смене")
    show_menu(message)


@bot.message_handler(commands=['menu'])
def show_menu(message):
    """Показывает контекстное меню."""
    keyboard = create_contextual_keyboard(message.chat.id, message.from_user.id)
    bot.send_message(message.chat.id, "Навигационное меню:", reply_markup=keyboard)


@bot.message_handler(commands=['training_start'])
def training_start(message):
    """Включает режим тренировки для пользователя."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = get_username(message.from_user)

    if chat_id not in chat_data: chat_data[chat_id] = {'users': {}}
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)

    chat_data[chat_id]['users'][user_id]['in_training'] = True
    bot.reply_to(message, "✅ Режим тренировки активирован. Ваши действия не будут учитываться. Для выхода: /training_stop.")


@bot.message_handler(commands=['training_stop'])
def training_stop(message):
    """Отключает режим тренировки."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_data.get(chat_id, {}).get('users', {}).get(user_id):
        chat_data[chat_id]['users'][user_id]['in_training'] = False
    bot.reply_to(message, "☑️ Режим тренировки отключен.")


# --- Обработчики кнопок меню ---
@bot.message_handler(func=lambda m: m.text == "Скрыть меню")
def hide_menu(message):
    bot.send_message(message.chat.id, "Меню скрыто. Вызовите /menu, чтобы показать его снова.", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "🚀 Встать в смену")
def menu_take_shift(message):
    handle_start(message)

@bot.message_handler(func=lambda m: m.text == "☕️ Уйти на перерыв")
def menu_take_break(message):
    handle_break_request(message)

@bot.message_handler(func=lambda m: m.text == "✅ Я вернулся")
def menu_return_from_break(message):
    handle_user_return(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda m: m.text in ["⭐️ Моя статистика", "ℹ️ Сводка по смене"])
def menu_get_stats(message):
    chat_id = message.chat.id
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        bot.reply_to(message, "Смена еще не началась, статистика недоступна.")
        return

    report_lines = get_report_lines(chat_id, data, full_report=False)
    final_report = "\n".join(report_lines)
    bot.send_message(chat_id, final_report, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🚨 Отчет по прогульщикам")
@admin_required
def menu_get_truants(message):
    chat_id = message.chat.id
    users = chat_data.get(chat_id, {}).get('users', {})
    now = datetime.datetime.now(moscow_tz)
    
    if not users:
        bot.reply_to(message, "В базе данных пока нет пользователей.")
        return

    truants = [f"❗️ {user_data['username']} - неактивен {int((now - user_data['last_voice_time']).total_seconds() / 60)} мин."
               for user_id, user_data in users.items() if user_data.get('last_voice_time') and (now - user_data['last_voice_time']).total_seconds() / 60 > VOICE_TIMEOUT_MINUTES]
    
    report = "🚨 **Отчет по неактивным:**\n\n" + "\n".join(truants) if truants else "✅ Все недавние пользователи были активны."
    bot.send_message(chat_id, report, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "🆘 Помощь")
def menu_get_help(message):
    help_text = """
🆘 **Справка по боту** 🆘
Я бот для контроля активности ведущих.
- **Старт**: Отправьте ГС или команду `/start`.
- **Перерыв**: Используйте кнопки. Длительность: 15 мин.
- **ГС**: >7 сек, пауза >2 мин.
**Команды**:
`/menu` - Показать меню.
`/training_start` - Войти в режим тренировки.
`/training_stop` - Выйти из тренировки.
"""
    bot.reply_to(message, help_text, parse_mode="Markdown")
    

@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in BREAK_KEYWORDS))
def handle_break_request(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

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
        'pre_return_warning_sent': False
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
    save_history_event(chat_id, user_id, user['username'], f"Ушел на перерыв ({user['breaks_count']}-й раз)")
    show_menu(message)


@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message.from_user)
    now = datetime.datetime.now(moscow_tz)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': now, 'chat_title': get_chat_title(chat_id)}
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)
    user = chat_data[chat_id]['users'][user_id]

    if user['in_training']:
        bot.reply_to(message, f"Тренировка: получено ГС, длина {message.voice.duration} сек.")
        return

    if user.get('on_break'): handle_user_return(chat_id, user_id)

    if user.get('reminder_sent_at'):
        user['response_times'].append((now - user['reminder_sent_at']).total_seconds() / 60)
        user['reminder_sent_at'] = None

    voice_duration = message.voice.duration
    save_history_event(chat_id, user_id, username, f"Прислал ГС ({voice_duration} сек)")
    user['voice_durations'].append(voice_duration)

    if voice_duration < MIN_VOICE_SECONDS:
        bot.send_message(chat_id, random.choice(soviet_phrases["too_short"]))
        return

    last_voice = user.get('last_voice_time')
    if last_voice and (now - last_voice).total_seconds() < VOICE_COOLDOWN_SECONDS:
        remaining_cooldown = int(VOICE_COOLDOWN_SECONDS - (now - last_voice).total_seconds())
        bot.reply_to(message, f"Слишком часто! Следующее ГС можно через {remaining_cooldown} сек.")
        save_history_event(chat_id, user_id, username, "Прислал ГС (флуд)")
        return

    if last_voice: user['voice_deltas'].append((now - last_voice).total_seconds() / 60)
    else: user['first_voice_time'] = now

    user['count'] += 1
    user['last_voice_time'] = now
    
    if "accept" in soviet_phrases:
        bot.reply_to(message, random.choice(soviet_phrases["accept"]))

    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")
        show_menu(message)


@bot.message_handler(func=lambda m: m.text)
def handle_text_message(message):
    user_id = message.from_user.id
    user_on_break = chat_data.get(message.chat.id, {}).get('users', {}).get(user_id, {}).get('on_break')
    
    if any(word in message.text.lower() for word in RETURN_CONFIRM_WORDS) and user_on_break:
        handle_user_return(message.chat.id, user_id)

# ========================================
#           ОТЧЕТЫ, АНАЛИТИКА И ПЛАНИРОВЩИК
# ========================================
def check_users_activity():
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id: continue
        
        user = data['users'][main_id]
        
        if user.get('on_break') and not user.get('pre_return_warning_sent'):
            if (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                bot.send_message(chat_id, f"⏰ {user['username']}, твой {BREAK_DURATION_MINUTES}-минутный перерыв закончился. Пора возвращаться!")
                user['pre_return_warning_sent'] = True
        
        last_voice = user.get('last_voice_time')
        if not user.get('on_break') and last_voice and not user.get('reminder_sent_at'):
            if (now - last_voice).total_seconds() / 60 > VOICE_TIMEOUT_MINUTES:
                bot.send_message(chat_id, f"🚨 {user['username']}, вы давно не выходили в эфир. Как дела?")
                user['reminder_sent_at'] = now
                save_history_event(chat_id, main_id, user['username'], "Отправлено напоминание о простое")


def get_report_lines(chat_id, data, full_report=False):
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}): return ["Главный не назначен или нет данных."]
    
    user = data['users'][main_id]
    now = datetime.datetime.now(moscow_tz)

    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    short_voices_perc = (sum(1 for d in user['voice_durations'] if d < 10) / len(user['voice_durations']) * 100) if user['voice_durations'] else 0
    avg_response_time = sum(user['response_times']) / len(user['response_times']) if user['response_times'] else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    first_voice_str = user.get('first_voice_time').strftime('%H:%M') if user.get('first_voice_time') else "N/A"
    last_voice_str = user.get('last_voice_time').strftime('%H:%M') if user.get('last_voice_time') else "N/A"

    tag = "#Отчет_Смены" if full_report else "#Промежуточный_Отчет"
    report = [
        f"📋 {tag} ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
        f"🏢 Чат: {get_chat_title(chat_id)}",
        f"🎤 Ведущий: {user['username']}",
        "---",
        f"🗣️ **Голосовых:** {user['count']} из {EXPECTED_VOICES_PER_SHIFT} ({user['count'] / EXPECTED_VOICES_PER_SHIFT:.0%})",
        f"☕ **Перерывов:** {user['breaks_count']}",
        f"⏳ **Опозданий с перерыва:** {user['late_returns']}",
        "---",
        "**Статистика активности:**",
        f"📈 Средний ритм: {avg_delta:.1f} мин/ГС",
        f"🔇 Макс. пауза: {max_pause:.1f} мин.",
        f"⚡️ Реакция на напом.: {avg_response_time:.1f} мин." if avg_response_time else "⚡️ Напоминаний не было",
        "---",
        "**Качество (косвенно):**",
        f"📏 Ср. длина ГС: {avg_duration:.1f} сек.",
        f"🤏 Коротких ГС (<10с): {short_voices_perc:.0f}%"
    ]
    return report

def generate_analytical_summary(user_data):
    summary = ["\n---", "🧠 **Анализ смены:**"]
    
    if user_data.get('voice_deltas'):
        if max(user_data['voice_deltas']) > VOICE_TIMEOUT_MINUTES * 1.5:
            summary.append("•  зона роста: были длинные паузы в эфире.")
        else:
            summary.append("• сильная сторона: хороший, стабильный ритм.")

    if user_data.get('response_times'):
        if sum(user_data['response_times']) / len(user_data['response_times']) < 3:
            summary.append("• сильная сторона: отличная реакция на напоминания.")
        else:
            summary.append("• зона роста: стоит быстрее реагировать на уведомления.")
            
    if user_data.get('late_returns', 0) > 0:
        summary.append(f"• зона роста: зафиксировано {user_data['late_returns']} опоздание(й).")
    
    return "\n".join(summary) if len(summary) > 2 else "\nОтличная работа, замечаний нет!"

def send_end_of_shift_reports():
    logging.info("Начало отправки итоговых отчетов...")
    for chat_id, data in chat_data.items():
        main_id = data.get('main_id')
        if not main_id: continue
        
        main_user_data = data.get('users', {}).get(main_id)
        if not main_user_data: continue
        
        report_lines = get_report_lines(chat_id, data, full_report=True)
        analytical_summary = generate_analytical_summary(main_user_data)
        final_report = "\n".join(report_lines) + "\n" + analytical_summary
        
        try:
            bot.send_message(chat_id, final_report, parse_mode="Markdown")
            if ADMIN_REPORT_CHAT_ID:
                bot.send_message(ADMIN_REPORT_CHAT_ID, final_report, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат {chat_id}: {e}")
            
    chat_data.clear()
    user_history.clear()
    logging.info("Данные смены очищены, подготовка к новой смене.")

def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("23:50", "Europe/Moscow").do(send_end_of_shift_reports)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========================================
#           ЗАПУСК БОТА
# ========================================
if __name__ == '__main__':
    logging.info("🤖 Каноничная финальная версия бота запущена...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
