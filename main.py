# -*- coding: utf-8 -*-
"""
Финальная версия с расширенными отчетами и HR-функциями (тренировочный режим, анализ).
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
VOICE_COOLDOWN_SECONDS = 120
BREAK_DURATION_MINUTES = 15
BREAK_DELAY_MINUTES = 60

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
            if user_id == ADMIN_CHAT_ID: # Супер-админ
                return func(message)
            admins = [admin.user.id for admin in bot.get_chat_administrators(message.chat.id)]
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
    return f"@{user.username}" if user.username else user.first_name

def init_user_data(user_id, username):
    """Инициализация словаря для нового пользователя."""
    return {
        'username': username, 'count': 0, 'on_break': False,
        'breaks_count': 0, 'late_returns': 0, 'last_voice_time': None,
        'last_break_time': None, 'last_remind_time': None,
        'reminder_sent_at': None, 'response_times': [],
        'waiting_return_confirm': False, 'achievements': set(),
        'voice_deltas': [], 'voice_durations': [], 'kudos': 0,
        'in_training': False, 'first_voice_time': None
    }

def handle_user_return(chat_id, user_id):
    """Общая логика для обработки возврата с перерыва."""
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if not user or not user.get('on_break'): return

    now = datetime.datetime.now(moscow_tz)
    break_duration_minutes = (now - user['break_start_time']).total_seconds() / 60
    
    user['on_break'] = False
    user['waiting_return_confirm'] = False
    
    if break_duration_minutes > BREAK_DURATION_MINUTES:
        user['late_returns'] += 1
        bot.send_message(chat_id, f"✅ {user['username']}, с возвращением! Ты опоздал на {int(break_duration_minutes - BREAK_DURATION_MINUTES)} мин.")
    else:
        bot.send_message(chat_id, f"👍 {user['username']}, с возвращением! Молодец, что вернулся вовремя.")
    
    save_history_event(chat_id, user_id, user['username'], f"Вернулся с перерыва (длительность {break_duration_minutes:.1f} мин)")

# ... и другие вспомогательные функции ...

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ И ОБРАБОТЧИКИ
# ========================================
@bot.message_handler(commands=['training_start'])
def training_start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = get_username(message.from_user)
    
    if chat_id not in chat_data:
        chat_data[chat_id] = {'users': {}}
    if user_id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)
        
    chat_data[chat_id]['users'][user_id]['in_training'] = True
    bot.reply_to(message, "✅ Режим тренировки активирован. Ваши действия не будут учитываться в общей статистике. Бот будет давать вам подсказки. Для выхода используйте /training_stop.")

@bot.message_handler(commands=['training_stop'])
def training_stop(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_data.get(chat_id, {}).get('users', {}).get(user_id):
        chat_data[chat_id]['users'][user_id]['in_training'] = False
    bot.reply_to(message, "☑️ Режим тренировки отключен. Вы вернулись к обычной работе.")

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
    
    # Логика для тренировочного режима
    if user['in_training']:
        bot.reply_to(message, f"Тренировка: получено голосовое, длина {message.voice.duration} сек. Минимальная норма: {MIN_VOICE_SECONDS} сек. Отлично!")
        return

    # Если на перерыве - возвращаем
    if user.get('on_break'):
        handle_user_return(chat_id, user_id)
        
    # Проверка реакции на напоминание
    if user.get('reminder_sent_at'):
        response_time = (now - user['reminder_sent_at']).total_seconds() / 60
        user['response_times'].append(response_time)
        user['reminder_sent_at'] = None # Сбрасываем

    voice_duration = message.voice.duration
    save_history_event(chat_id, user_id, username, f"Прислал голосовое ({voice_duration} сек)")
    user['voice_durations'].append(voice_duration)

    if voice_duration < MIN_VOICE_SECONDS:
        bot.send_message(chat_id, random.choice(soviet_phrases["too_short"]))
        return

    last_voice = user.get('last_voice_time')
    if last_voice and (now - last_voice).total_seconds() < VOICE_COOLDOWN_SECONDS:
        bot.reply_to(message, f"Слишком часто! Следующее голосовое будет засчитано через {int(VOICE_COOLDOWN_SECONDS - (now - last_voice).total_seconds())} сек.")
        return

    if last_voice:
        user['voice_deltas'].append((now - last_voice).total_seconds() / 60)
    else: # Первое голосовое
        user['first_voice_time'] = now

    user['count'] += 1
    user['last_voice_time'] = now
    
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое голосовое!", reply_markup=create_main_keyboard())

# ... (остальные обработчики, команды и планировщик) ...

# ========================================
#           ОТЧЕТЫ И АНАЛИТИКА
# ========================================

def get_report_lines(chat_id, data, full_report=False):
    main_id = data.get('main_id')
    if not main_id: return ["Главный не назначен."]
    user = data['users'][main_id]
    
    # Расчет всех метрик
    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    short_voices_perc = (sum(1 for d in user['voice_durations'] if d < 10) / len(user['voice_durations']) * 100) if user['voice_durations'] else 0
    avg_response_time = sum(user['response_times']) / len(user['response_times']) if user['response_times'] else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    first_voice_str = user.get('first_voice_time', now).strftime('%H:%M')
    last_voice_str = user.get('last_voice_time', now).strftime('%H:%M')

    # Формирование отчета
    tag = "#Отчет_Смены" if full_report else "#Промежуточный_Отчет"
    report = [
        f"📋 {tag} ({data['shift_start'].strftime('%d.%m.%Y')})",
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
    
    # Анализ ритма
    if user_data['voice_deltas']:
        max_pause = max(user_data['voice_deltas'])
        if max_pause > VOICE_TIMEOUT_MINUTES * 1.5:
            summary.append("•  зона роста: были очень длинные паузы в эфире. Стоит поработать над равномерностью.")
        else:
            summary.append("• сильная сторона: хороший, стабильный ритм работы в течение смены.")

    # Анализ реакции
    if user_data['response_times']:
        avg_response = sum(user_data['response_times']) / len(user_data['response_times'])
        if avg_response < 3:
            summary.append("• сильная сторона: отличная реакция на напоминания, вы всегда на связи.")
        else:
            summary.append("• зона роста: стоит быстрее реагировать на уведомления о простое.")
            
    # Анализ опозданий
    if user_data['late_returns'] > 0:
        summary.append(f"• зона роста: зафиксировано {user_data['late_returns']} опоздание(й) с перерыва. Важно соблюдать тайминг.")
    
    if len(summary) == 1: # Если нечего добавить
        return "Отличная работа, замечаний нет!"
        
    return "\n".join(summary)


def send_end_of_shift_reports():
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
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат {chat_id}: {e}")
            
        shift_reports.append({"chat_id": chat_id, "report": final_report})
    
    chat_data.clear()
    user_history.clear()

# ========================================
#                ЗАПУСК БОТА
# ========================================

def run_scheduler():
    # ... (код планировщика)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.info("🤖 Бот (версия с HR-функциями) запущен...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
