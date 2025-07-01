# -*- coding: utf-8 -*-
"""
Финальная версия бота:
- Разделение отчетов: краткий промежуточный и подробный итоговый.
- Без меню, управление текстовыми командами.
- Ежедневный отчет в 10:00 МСК.
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
from telebot import types
from functools import wraps
from typing import Dict

# Импорт фраз
try:
    from phrases import (
        soviet_phrases,
        BREAK_KEYWORDS, RETURN_CONFIRM_WORDS
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

BOSS_ID = 196614680
ADMIN_REPORT_CHAT_ID = -1002645821302
STATS_FILE = 'user_stats.csv'

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

# ========================================
#      РАБОТА С ФАЙЛОМ СТАТИСТИКИ
# ========================================

def load_user_stats() -> Dict[int, Dict]:
    stats = {}
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'username', 'total_shifts', 'total_voices', 'total_breaks', 'total_lates'])
        return stats
    try:
        with open(STATS_FILE, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats[int(row['user_id'])] = {
                    'username': row['username'],
                    'total_shifts': int(row['total_shifts']),
                    'total_voices': int(row['total_voices']),
                    'total_breaks': int(row['total_breaks']),
                    'total_lates': int(row['total_lates'])
                }
    except Exception as e:
        logging.error(f"Ошибка при чтении файла статистики: {e}")
    return stats

def save_user_stats(all_stats: Dict[int, Dict]):
    try:
        with open(STATS_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'username', 'total_shifts', 'total_voices', 'total_breaks', 'total_lates'])
            for user_id, stats in all_stats.items():
                writer.writerow([user_id, stats.get('username', 'N/A'), stats.get('total_shifts', 0), stats.get('total_voices', 0), stats.get('total_breaks', 0), stats.get('total_lates', 0)])
    except IOError as e:
        logging.error(f"Ошибка при сохранении файла статистики: {e}")

def update_historical_stats(user_id: int, username: str, shift_data: dict):
    all_stats = load_user_stats()
    if user_id not in all_stats:
        all_stats[user_id] = {'username': username, 'total_shifts': 0, 'total_voices': 0, 'total_breaks': 0, 'total_lates': 0}

    all_stats[user_id]['username'] = username
    all_stats[user_id]['total_shifts'] += 1
    all_stats[user_id]['total_voices'] += shift_data.get('count', 0)
    all_stats[user_id]['total_breaks'] += shift_data.get('breaks_count', 0)
    all_stats[user_id]['total_lates'] += shift_data.get('late_returns', 0)
    
    save_user_stats(all_stats)

# ========================================
#           ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def is_admin(user_id, chat_id):
    if user_id == BOSS_ID: return True
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    except Exception as e:
        logging.error(f"Ошибка проверки администратора в чате {chat_id}: {e}")
        return False

def admin_required(func):
    @wraps(func)
    def wrapper(message):
        if not is_admin(message.from_user.id, message.chat.id):
            bot.reply_to(message, "⛔ Эту команду могут использовать только администраторы чата.")
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

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ
# ========================================

@bot.message_handler(commands=['start', 'старт'])
def handle_start(message):
    chat_id = message.chat.id
    from_user = message.from_user
    username = get_username(from_user)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'users': {}, 'shift_start': datetime.datetime.now(moscow_tz)}

    if from_user.id not in chat_data[chat_id]['users']:
        chat_data[chat_id]['users'][from_user.id] = init_user_data(from_user.id, username)

    if chat_data[chat_id].get('main_id') is not None:
        main_username = chat_data[chat_id].get('main_username', 'Неизвестно')
        bot.reply_to(message, f"Смена уже занята. Текущий главный: {main_username}.")
        return

    chat_data[chat_id]['main_id'] = from_user.id
    chat_data[chat_id]['main_username'] = username
    bot.send_message(chat_id, f"👑 {username}, вы заступили на смену! Удачи!")


@bot.message_handler(commands=['check', 'промежуточный'])
@admin_required
def admin_check_shift(message):
    chat_id = message.chat.id
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        bot.reply_to(message, "Смена еще не началась, статистика недоступна.")
        return

    main_id = data.get('main_id')
    user = data.get('users', {}).get(main_id)
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


@bot.message_handler(commands=['сводка'])
def my_total_stats(message):
    user_id = message.from_user.id
    username = get_username(message.from_user)
    all_stats = load_user_stats()
    user_stats = all_stats.get(user_id)

    if not user_stats:
        bot.reply_to(message, f"{username}, у вас пока нет сохраненной истории смен.")
        return

    report_text = (
        f"⭐️ **Общая статистика для {username}** ⭐️\n\n"
        f"👑 **Всего смен отработано:** {user_stats.get('total_shifts', 0)}\n"
        f"🗣️ **Всего голосовых записано:** {user_stats.get('total_voices', 0)}\n"
        f"☕️ **Всего перерывов:** {user_stats.get('total_breaks', 0)}\n"
        f"⏳ **Всего опозданий с перерыва:** {user_stats.get('total_lates', 0)}"
    )
    bot.reply_to(message, report_text)
    

@bot.message_handler(commands=['analyze'])
@admin_required
def admin_analyze_all_users(message):
    all_stats = load_user_stats()
    if not all_stats:
        bot.reply_to(message, "База данных статистики пуста. Пока некого анализировать.")
        return

    processed_users = []
    for user_id, stats in all_stats.items():
        total_shifts = stats.get('total_shifts', 0)
        if total_shifts == 0: continue
        avg_voices_per_shift = stats.get('total_voices', 0) / total_shifts
        lateness_ratio = (stats.get('total_lates', 0) / total_shifts) * 100
        processed_users.append({
            'username': stats.get('username', f'ID: {user_id}'),
            'avg_voices': avg_voices_per_shift,
            'lateness_percent': lateness_ratio,
            'shifts': total_shifts
        })

    processed_users.sort(key=lambda x: x['avg_voices'], reverse=True)
    report_lines = ["📊 **Общая сводка по всем сотрудникам**", "_(Отсортировано по ср. кол-ву ГС за смену)_\n"]
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    for i, user in enumerate(processed_users):
        rank_icon = medals.get(i, f"{i+1}.")
        report_lines.append(
            f"*{rank_icon}* {user['username']} — *Ср. ГС:* `{user['avg_voices']:.1f}` | *Опоздания:* `{user['lateness_percent']:.0f}%` | *Смен:* `{user['shifts']}`"
        )

    if not processed_users:
         report_lines.append("Нет сотрудников с отработанными сменами.")
    bot.send_message(message.chat.id, "\n".join(report_lines))

# ========================================
#           ОБРАБОТЧИКИ СООБЩЕНИЙ
# ========================================

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
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
    
    if "accept" in soviet_phrases:
        bot.reply_to(message, random.choice(soviet_phrases["accept"]))

    if chat_data[chat_id].get('main_id') is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")

@bot.message_handler(commands=['перерыв'])
def handle_break_command(message):
    handle_break_request(message)

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
    })
    bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
    
@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in RETURN_CONFIRM_WORDS))
def handle_return_message(message):
    user_id = message.from_user.id
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
        
        if user.get('on_break') and not user.get('pre_return_warning_sent', False):
            if user.get('break_start_time') and (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                bot.send_message(chat_id, random.choice(soviet_phrases.get("return_demand", ["Пора возвращаться."])))
                user['pre_return_warning_sent'] = True
        
        last_voice = user.get('last_voice_time')
        if not user.get('on_break') and last_voice and not user.get('reminder_sent_at'):
            if (now - last_voice).total_seconds() / 60 > VOICE_TIMEOUT_MINUTES:
                bot.send_message(chat_id, random.choice(soviet_phrases.get("voice_reminder", [f"🚨 {user['username']}, вы давно не выходили в эфир."])))
                user['reminder_sent_at'] = now

def generate_detailed_report(chat_id: int, data: dict) -> list:
    """Генерирует подробный отчет по итогам смены."""
    main_id = data.get('main_id')
    if not main_id or main_id not in data.get('users', {}): return ["Главный не был назначен."]
    
    user = data['users'][main_id]
    now = datetime.datetime.now(moscow_tz)

    avg_delta = sum(user['voice_deltas']) / len(user['voice_deltas']) if user['voice_deltas'] else 0
    avg_duration = sum(user['voice_durations']) / len(user['voice_durations']) if user['voice_durations'] else 0
    short_voices_perc = (sum(1 for d in user['voice_durations'] if d < 10) / len(user['voice_durations']) * 100) if user['voice_durations'] else 0
    avg_response_time = sum(user.get('response_times', [])) / len(user['response_times']) if user.get('response_times') else 0
    max_pause = max(user['voice_deltas']) if user['voice_deltas'] else 0
    plan_percent = (user['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0

    report = [
        f"📋 #Итоговый_Отчет_Смены ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
        f"🏢 Чат: {get_chat_title(chat_id)}",
        f"🎤 Ведущий: {user['username']}",
        "---",
        f"🗣️ **Голосовых:** {user['count']} из {EXPECTED_VOICES_PER_SHIFT} ({plan_percent:.0f}%)",
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

def generate_analytical_summary(user_data: dict) -> str:
    """Генерирует текстовый анализ работы ведущего."""
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
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id or main_id not in data.get('users', {}): continue
        
        main_user_data = data['users'][main_id]
        update_historical_stats(main_id, main_user_data['username'], main_user_data)
        
        report_lines = generate_detailed_report(chat_id, data)
        analytical_summary = generate_analytical_summary(main_user_data)
        final_report = "\n".join(report_lines) + "\n" + analytical_summary
        
        try:
            bot.send_message(chat_id, final_report)
            if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
                bot.send_message(ADMIN_REPORT_CHAT_ID, final_report)
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат {chat_id}: {e}")
            
    chat_data.clear()
    logging.info("Данные смены очищены.")

def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("10:00", "Europe/Moscow").do(send_end_of_shift_reports)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# ========================================
#           ЗАПУСК БОТА
# ========================================
if __name__ == '__main__':
    logging.info("🤖 Бот (версия без меню) запущен...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
            
