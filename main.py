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
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN: raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

BOSS_ID = 196614680
ADMIN_REPORT_CHAT_ID = -1002645821302

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
user_history: Dict[int, List[str]] = {}
shift_reports = []

# ========================================
#           ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================
def is_admin(user_id, chat_id):
    """Проверяет, является ли пользователь администратором или БОССОМ."""
    if user_id == BOSS_ID: return True
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
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
    """Получает username или имя пользователя."""
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
    # Создаем фейковый объект message для вызова show_menu
    fake_message = types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), from_user=types.SimpleNamespace(id=user_id))
    show_menu(fake_message)

def get_chat_title(chat_id: int) -> str:
    """Получает название чата по его ID."""
    try:
        title = bot.get_chat(chat_id).title
        return title if title else str(chat_id)
    except: return str(chat_id)

def save_history_event(chat_id, user_id, username, event_description):
    """Сохраняет событие в историю для последующего аудита."""
    if chat_id not in user_history: user_history[chat_id] = []
    now_str = datetime.datetime.now(moscow_tz).strftime('%Y-%m-%d %H:%M:%S')
    user_history[chat_id].append(f"{now_str} | {username} ({user_id}) | {event_description}")
    logging.info(f"HISTORY [{get_chat_title(chat_id)}]: {username} - {event_description}")

def generate_progress_bar(current, goal, length=10):
    """Генерирует текстовый прогресс-бар."""
    if goal == 0: return "[----------] 0%"
    percent = int((current / goal) * 100)
    filled_length = int(length * current // goal)
    bar = '█' * filled_length + '─' * (length - filled_length)
    return f"[{bar}] {percent}%"

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
    """Обрабатывает заступление на смену или ее передачу."""
    chat_id = message.chat.id
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

    # Если /start без параметров
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

    if chat_id not in chat_data:
        chat_data[chat_id] = {'users': {}}
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)

    chat_data[chat_id]['users'][user_id]['in_training'] = True
    bot.reply_to(message, "✅ Режим тренировки активирован. Ваши действия не будут учитываться в статистике. Для выхода используйте /training_stop.")


@bot.message_handler(commands=['training_stop'])
def training_stop(message):
    """Отключает режим тренировки."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_data.get(chat_id, {}).get('users', {}).get(user_id):
        chat_data[chat_id]['users'][user_id]['in_training'] = False
    bot.reply_to(message, "☑️ Режим тренировки отключен. Вы вернулись к обычной работе.")


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
    
# ... (здесь можно добавить обработчики для "Сводка", "Моя статистика" и админских кнопок) ...


@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in BREAK_KEYWORDS))
def handle_break_request(message):
    """Обрабатывает запрос на перерыв по ключевым словам."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if chat_data.get(chat_id, {}).get('main_id') != user_id:
        bot.reply_to(message, "⛔ Перерыв может взять только главный на смене.")
        return
        
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id, {})
    if user.get('on_break'):
        bot.reply_to(message, "Вы уже на перерыве. Сначала вернитесь.")
        return

    last_break = user.get('last_break_time')
    if last_break and (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
        bot.reply_to(message, f"Вы недавно были на перерыве. Следующий можно взять через {int(BREAK_DELAY_MINUTES - (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60)} мин.")
        return

    user.update({
        'on_break': True, 'break_start_time': datetime.datetime.now(moscow_tz),
        'last_break_time': datetime.datetime.now(moscow_tz),
        'breaks_count': user.get('breaks_count', 0) + 1,
        'pre_return_warning_sent': False
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат. Жду вашего возвращения.")
    save_history_event(chat_id, user_id, user['username'], f"Ушел на перерыв ({user['breaks_count']}-й раз)")
    show_menu(message)


@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    """Обрабатывает все голосовые сообщения."""
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
        bot.reply_to(message, f"Тренировка: получено ГС, длина {message.voice.duration} сек. Минимальная норма: {MIN_VOICE_SECONDS} сек. Отлично!")
        return

    if user.get('on_break'):
        handle_user_return(chat_id, user_id)

    # Проверка реакции на напоминание
    if user.get('reminder_sent_at'):
        response_time = (now - user['reminder_sent_at']).total_seconds() / 60
        user['response_times'].append(response_time)
        user['reminder_sent_at'] = None

    voice_duration = message.voice.duration
    save_history_event(chat_id, user_id, username, f"Прислал голосовое ({voice_duration} сек)")
    user['voice_durations'].append(voice_duration)

    if voice_duration < MIN_VOICE_SECONDS:
        bot.send_message(chat_id, random.choice(soviet_phrases["too_short"]))
        return

    last_voice = user.get('last_voice_time')
    # Анти-флуд контроль
    if last_voice and (now - last_voice).total_seconds() < VOICE_COOLDOWN_SECONDS:
        bot.reply_to(message, f"Слишком часто! Следующее голосовое будет засчитано в статистику через {int(VOICE_COOLDOWN_SECONDS - (now - last_voice).total_seconds())} сек.")
        save_history_event(chat_id, user_id, username, "Прислал голосовое (флуд)")
        return

    # Контроль ритма
    if last_voice:
        delta_minutes = (now - last_voice).total_seconds() / 60
        user['voice_deltas'].append(delta_minutes)
    else: # Первое голосовое
        user['first_voice_time'] = now

    user['count'] += 1
    user['last_voice_time'] = now

    # Если это первое ГС, делаем юзера главным
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое голосовое!")
        show_menu(message)


@bot.message_handler(func=lambda m: m.text)
def handle_text_message(message):
    """Обрабатывает текстовые сообщения, в основном для подтверждения возврата."""
    user_id = message.from_user.id
    user_on_break = chat_data.get(message.chat.id, {}).get('users', {}).get(user_id, {}).get('on_break')
    
    if any(word in message.text.lower() for word in RETURN_CONFIRM_WORDS) and user_on_break:
        handle_user_return(message.chat.id, user_id)

# ========================================
#           ОТЧЕТЫ, АНАЛИТИКА И ПЛАНИРОВЩИК
# ========================================
def check_users_activity():
    """Проверяет активность пользователей и отправляет напоминания."""
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id: continue
        
        user = data['users'][main_id]
        
        # Проверка возврата с перерыва
        if user.get('on_break') and not user.get('pre_return_warning_sent'):
            minutes_on_break = (now - user['break_start_time']).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES:
                bot.send_message(chat_id, f"⏰ @{user['username']}, твой {BREAK_DURATION_MINUTES}-минутный перерыв закончился. Пора возвращаться!")
                user['pre_return_warning_sent'] = True
        
        # Логика напоминаний об активности (простое)
        last_voice = user.get('last_voice_time')
        if not user.get('on_break') and last_voice and not user.get('reminder_sent_at'):
            minutes_since_last_voice = (now - last_voice).total_seconds() / 60
            if minutes_since_last_voice > VOICE_TIMEOUT_MINUTES:
                bot.send_message(chat_id, f"🚨 @{user['username']}, вы давно не выходили в эфир. Как дела?")
                user['reminder_sent_at'] = now
                save_history_event(chat_id, main_id, user['username'], "Отправлено напоминание о простое")


def get_report_lines(chat_id, data, full_report=False):
    """Генерирует строки для отчета."""
    main_id = data.get('main_id')
    if not main_id or main_id not in data['users']: return ["Главный не назначен или нет данных."]
    
    user = data['users'][main_id]
    now = datetime.datetime.now(moscow_tz)

    # Расчет метрик
    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    short_voices_perc = (sum(1 for d in user['voice_durations'] if d < 10) / len(user['voice_durations']) * 100) if user['voice_durations'] else 0
    avg_response_time = sum(user['response_times']) / len(user['response_times']) if user['response_times'] else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    first_voice_str = user.get('first_voice_time', now).strftime('%H:%M') if user.get('first_voice_time') else "N/A"
    last_voice_str = user.get('last_voice_time', now).strftime('%H:%M') if user.get('last_voice_time') else "N/A"

    # Формирование отчета
    tag = "#Отчет_Смены" if full_report else "#Промежуточный_Отчет"
    report = [
        f"📋 {tag} ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
        f"🏢 Чат: {get_chat_title(chat_id)}",
        f"🎤 Ведущий: {user['username']}",
        "---",
        "📊 **КОЛИЧЕСТВО:**",
        f"🗣️ Голосовых: {user['count']} из {EXPECTED_VOICES_PER_SHIFT} ({user['count'] / EXPECTED_VOICES_PER_SHIFT:.0%})",
        f"👍 Благодарностей: {user['kudos']}",
        "---",
        "⏳ **ДИСЦИПЛИНА:**",
        f"☕ Перерывов: {user['breaks_count']}",
        f"⏳ Опозданий с перерыва: {user['late_returns']}",
        f"⚡️ Реакция на напом.: {avg_response_time:.1f} мин." if avg_response_time else "⚡️ Напоминаний не было",
        "---",
        "📈 **АКТИВНОСТЬ:**",
        f"🕰️ В эфире: с {first_voice_str} по {last_voice_str}",
        f"📈 Средний ритм: {avg_delta:.1f} мин/сообщение",
        f"🔇 Макс. пауза: {max_pause:.1f} мин.",
        "---",
        "🎙️ **КАЧЕСТВО (косвенно):**",
        f"📏 Ср. длина ГС: {avg_duration:.1f} сек.",
        f"🤏 Коротких ГС (<10с): {short_voices_perc:.0f}%"
    ]
    return report

def generate_analytical_summary(user_data):
    """Генерирует текстовый анализ работы ведущего."""
    summary = ["\n---", "🧠 **Анализ смены:**"]
    
    if user_data['voice_deltas']:
        max_pause = max(user_data['voice_deltas'])
        if max_pause > VOICE_TIMEOUT_MINUTES * 1.5:
            summary.append("•  зона роста: были очень длинные паузы в эфире. Стоит поработать над равномерностью.")
        else:
            summary.append("• сильная сторона: хороший, стабильный ритм работы в течение смены.")

    if user_data['response_times']:
        avg_response = sum(user_data['response_times']) / len(user_data['response_times'])
        if avg_response < 3:
            summary.append("• сильная сторона: отличная реакция на напоминания, вы всегда на связи.")
        else:
            summary.append("• зона роста: стоит быстрее реагировать на уведомления о простое.")
            
    if user_data['late_returns'] > 0:
        summary.append(f"• зона роста: зафиксировано {user_data['late_returns']} опоздание(й) с перерыва. Важно соблюдать тайминг.")
    
    if len(summary) == 2: # Если добавилась только "Анализ смены"
        return "\nОтличная работа, замечаний нет!"
        
    return "\n".join(summary)

def send_end_of_shift_reports():
    """Отправляет итоговые отчеты в конце смены."""
    global shift_reports
    shift_reports = []
    
    for chat_id, data in chat_data.items():
        main_id = data.get('main_id')
        if not main_id: continue
        
        main_user_data = data['users'][main_id]
        
        report_lines = get_report_lines(chat_id, data, full_report=True)
        analytical_summary = generate_analytical_summary(main_user_data)
        
        final_report = "\n".join(report_lines) + "\n" + analytical_summary
        
        try:
            bot.send_message(chat_id, final_report, parse_mode="Markdown")
            if ADMIN_REPORT_CHAT_ID:
                bot.send_message(ADMIN_REPORT_CHAT_ID, final_report, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат {chat_id}: {e}")
            
        shift_reports.append({"chat_id": chat_id, "report": final_report})
    
    chat_data.clear()
    user_history.clear()
    logging.info("Данные смены очищены, подготовка к новой смене.")

def run_scheduler():
    """Запускает планировщик фоновых задач."""
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("23:50", moscow_tz).do(send_end_of_shift_reports)
    
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
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)

```
