# -*- coding: utf-8 -*-
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
from telebot import types
from functools import wraps
from typing import Dict, List, Optional

# Импорт фраз
try:
    from phrases import soviet_phrases, BREAK_KEYWORDS, RETURN_CONFIRM_WORDS
except ImportError:
    logging.warning("Файл 'phrases.py' не найден. Используются значения по умолчанию.")
    BREAK_KEYWORDS = ["перерыв"]
    RETURN_CONFIRM_WORDS = ["вернулся"]
    soviet_phrases = {"too_short": ["Слишком коротко!"], "accept": ["Принято."], "not_your_menu": ["Не для вас."]}

# ========================================
#           НАСТРОЙКИ И ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

BOSS_ID = 196614680
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
user_history: Dict[int, list] = {}

# ========================================
#      РАБОТА С ФАЙЛОМ СТАТИСТИКИ
# ========================================

def load_user_stats() -> Dict[int, Dict]:
    stats = {}
    if not os.path.exists(STATS_FILE):
        return stats
    try:
        with open(STATS_FILE, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Пропускаем заголовок
            for row in reader:
                user_id, shifts, voices, breaks, lates = row
                stats[int(user_id)] = {'total_shifts': int(shifts), 'total_voices': int(voices), 'total_breaks': int(breaks), 'total_lates': int(lates)}
    except Exception as e:
        logging.error(f"Ошибка при чтении файла статистики: {e}")
    return stats

def save_user_stats(all_stats: Dict[int, Dict]):
    try:
        with open(STATS_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['user_id', 'total_shifts', 'total_voices', 'total_breaks', 'total_lates'])
            for user_id, stats in all_stats.items():
                writer.writerow([user_id, stats.get('total_shifts', 0), stats.get('total_voices', 0), stats.get('total_breaks', 0), stats.get('total_lates', 0)])
    except IOError as e:
        logging.error(f"Ошибка при сохранении файла статистики: {e}")

def update_historical_stats(user_id: int, shift_data: dict):
    all_stats = load_user_stats()
    if user_id not in all_stats:
        all_stats[user_id] = {'total_shifts': 0, 'total_voices': 0, 'total_breaks': 0, 'total_lates': 0}
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
        'pre_return_warning_sent': False, 'reminder_sent_at': None, 'response_times': [],
        'voice_deltas': [], 'voice_durations': [],
        'in_training': False, 'first_voice_time': None,
        'break_start_time': None, 'menu_message_id': None
    }

# ========================================
#           ЛОГИКА INLINE МЕНЮ (НОВОЕ)
# ========================================

def get_menu_text(user_data: dict) -> str:
    """Генерирует текст для меню-сообщения."""
    if user_data.get('on_break'):
        break_end_time = user_data['break_start_time'] + datetime.timedelta(minutes=BREAK_DURATION_MINUTES)
        return f"☕️ *На перерыве.* Ведущий: {user_data['username']}\nВернуться в: {break_end_time.strftime('%H:%M:%S')}"
    else:
        return f"🎤 *На смене.* Ведущий: {user_data['username']}\nГС: {user_data['count']} | Перерывы: {user_data['breaks_count']}"

def create_main_inline_keyboard(user_data: dict) -> types.InlineKeyboardMarkup:
    """Создает inline-клавиатуру для меню-сообщения."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    if user_data.get('on_break'):
        markup.add(types.InlineKeyboardButton("✅ Я вернулся", callback_data="break_return"))
    else:
        markup.add(types.InlineKeyboardButton("☕️ Уйти на перерыв", callback_data="break_start"))
    
    markup.add(types.InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats"))
    return markup

def send_or_update_menu(chat_id: int, user_id: int):
    """Отправляет или обновляет сообщение с inline-меню."""
    if chat_id not in chat_data or user_id not in chat_data[chat_id]['users']:
        return
    
    data = chat_data[chat_id]
    user_data = data['users'][user_id]
    menu_text = get_menu_text(user_data)
    keyboard = create_main_inline_keyboard(user_data)
    
    menu_message_id = user_data.get('menu_message_id')

    try:
        if menu_message_id:
            bot.edit_message_text(chat_id=chat_id, message_id=menu_message_id, text=menu_text, reply_markup=keyboard)
        else:
            msg = bot.send_message(chat_id, menu_text, reply_markup=keyboard)
            user_data['menu_message_id'] = msg.message_id
    except Exception as e:
        logging.error(f"Не удалось отправить/обновить меню в чате {chat_id}: {e}")
        if 'message to edit not found' in str(e) or 'message not found' in str(e):
             # Если сообщение было удалено, отправляем новое
             msg = bot.send_message(chat_id, menu_text, reply_markup=keyboard)
             user_data['menu_message_id'] = msg.message_id

# ========================================
#           ОСНОВНЫЕ КОМАНДЫ И ОБРАБОТЧИКИ
# ========================================

@bot.message_handler(commands=['start', 'старт'])
def handle_start(message):
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
    bot.send_message(chat_id, f"👑 {username}, вы заступили на смену! Ниже ваш пульт управления.")
    save_history_event(chat_id, from_user.id, username, "Стал главным на смене")
    send_or_update_menu(chat_id, from_user.id)


@bot.message_handler(commands=['check', 'промежуточный'])
@admin_required
def admin_check_shift(message):
    """(Только для админов) Показывает текущую сводку по смене."""
    chat_id = message.chat.id
    data = chat_data.get(chat_id)

    if not data or not data.get('main_id'):
        bot.reply_to(message, "Смена еще не началась, статистика недоступна.")
        return

    report_lines = get_report_lines(chat_id, data, full_report=False)
    final_report = "\n".join(report_lines)
    bot.send_message(chat_id, final_report)


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

    if user.get('on_break'):
        handle_user_return(chat_id, user_id)

    voice_duration = message.voice.duration
    save_history_event(chat_id, user_id, username, f"Прислал ГС ({voice_duration} сек)")
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

    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС! Ниже ваш пульт управления.")
        send_or_update_menu(chat_id, user_id)
    
    if chat_data[chat_id]['main_id'] == user_id:
        send_or_update_menu(chat_id, user_id)


# ========================================
#           ОБРАБОТЧИК КНОПОК (НОВЫЙ)
# ========================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = chat_data.get(chat_id, {})
    main_id = data.get('main_id')

    # Проверяем, что кнопку нажал именно главный на смене
    if user_id != main_id:
        bot.answer_callback_query(call.id, text=random.choice(soviet_phrases.get("not_your_menu", ["Не для вас."])), show_alert=True)
        return
    
    user_data = data.get('users', {}).get(user_id)
    if not user_data:
        bot.answer_callback_query(call.id, "Ошибка: не найдены данные пользователя.")
        return
    
    # --- Логика кнопок ---
    if call.data == 'break_start':
        last_break = user_data.get('last_break_time')
        if last_break and (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
            remaining = int(BREAK_DELAY_MINUTES - (datetime.datetime.now(moscow_tz) - last_break).total_seconds() / 60)
            bot.answer_callback_query(call.id, f"Еще рано! Следующий перерыв через {remaining} мин.", show_alert=True)
            return

        user_data.update({
            'on_break': True, 'break_start_time': datetime.datetime.now(moscow_tz),
            'last_break_time': datetime.datetime.now(moscow_tz),
            'breaks_count': user_data.get('breaks_count', 0) + 1,
            'pre_return_warning_sent': False
        })
        save_history_event(chat_id, user_id, user_data['username'], f"Ушел на перерыв ({user_data['breaks_count']}-й раз)")
        bot.answer_callback_query(call.id, f"Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
    
    elif call.data == 'break_return':
        handle_user_return(chat_id, user_id)
        bot.answer_callback_query(call.id, "С возвращением!")

    elif call.data == 'my_stats':
        all_stats = load_user_stats()
        stats = all_stats.get(user_id)
        if not stats:
            text = "У вас пока нет общей статистики."
        else:
            text = (
                f"⭐ Общая статистика для {get_username(call.from_user)} ⭐\n\n"
                f"👑 Смен отработано: {stats.get('total_shifts', 0)}\n"
                f"🗣️ Голосовых записано: {stats.get('total_voices', 0)}\n"
                f"☕️ Перерывов взято: {stats.get('total_breaks', 0)}\n"
                f"⏳ Опозданий с перерыва: {stats.get('total_lates', 0)}"
            )
        bot.answer_callback_query(call.id) # Просто чтобы кнопка перестала "грузиться"
        bot.send_message(chat_id, text, reply_to_message_id=call.message.message_id)

    # После любого действия обновляем меню
    send_or_update_menu(chat_id, user_id)

# ========================================
#           ОТЧЕТЫ, АНАЛИТИКА И ПЛАНИРОВЩИК
# ========================================
# (Функции get_report_lines, generate_analytical_summary, check_users_activity, send_end_of_shift_reports, run_scheduler, и __main__ остаются такими же, как в предыдущей версии)

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
    
    plan_percent = (user['count'] / EXPECTED_VOICES_PER_SHIFT * 100) if EXPECTED_VOICES_PER_SHIFT > 0 else 0

    tag = "#Отчет_Смены" if full_report else "#Промежуточный_Отчет"
    report = [
        f"📋 {tag} ({data.get('shift_start', now).strftime('%d.%m.%Y')})",
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
        
        update_historical_stats(main_id, main_user_data)
        
        report_lines = get_report_lines(chat_id, data, full_report=True)
        analytical_summary = generate_analytical_summary(main_user_data)
        final_report = "\n".join(report_lines) + "\n" + analytical_summary
        
        try:
            bot.send_message(chat_id, final_report, parse_mode="Markdown")
            if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
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

if __name__ == '__main__':
    logging.info("🤖 Каноничная финальная версия бота (с inline-меню) запущена...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
