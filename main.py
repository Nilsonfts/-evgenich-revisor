# -*- coding: utf-8 -*-
"""
Многофункциональный Telegram-бот для контроля смен, голосовых, перерывов, отчетов.
Версия с геймификацией, кнопками, гибкой настройкой и уведомлениями для админа.
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
#                БАНКИ ФРАЗ И ДОСТИЖЕНИЙ
# ========================================
# ... (банки фраз остаются без изменений, для краткости скрыты) ...
welcome_phrases = [
    "🎙️ Добро пожаловать, ведущий! Эфир ждет не болтовни, а работы.", "📻 Я тут, чтобы следить за твоей дисциплиной. Готовь голосовые.",
    "🕵️‍♂️ Я контролирую эфир. Не подведи.", "🔔 Теперь за тобой наблюдают. Не расслабляйся.",
    "🎤 Твой голос – твой KPI. Хватит халтуры, работаем!", "🚀 Не забудь: голосовое не будет – премии не будет.",
    "📝 Всё под контролем, каждое слово на счету.", "⏳ Время работает против тебя, если ты молчишь.",
]
soviet_phrases = {
    "voice_reminder": ["😡 Где голосовое? Пинка получишь сейчас!", "⛔️ Ты что, бессмертный? Голосовое или по жопе!"],
    "scary_reminder": ["👿 Следующее напоминание — с ремнем и выездом в лес.", "🪓 Ты доиграешься, если не пришлёшь голосовое."],
    "break_acknowledgement": ["☕ Перерыв засчитан, {username}. Смотри, чтобы не затянулся.", "🍔 Быстро перекуси и назад работать."],
    "break_too_soon": ["❌ Не наглей! Перерыв только раз в час. Терпи ещё {minutes} мин. Не раскисай!", "🕐 Ты недавно отдыхал. Ещё рано, работай!"],
    "too_short": ["🗑️ Ты это сейчас всерьёз? Голосовое меньше 7 секунд — даже читать стыдно.", "⏳ Такой короткий текст даже ёжик бы не принял."],
    "accept": ["✅ Принято. Следи за сменой, не расслабляйся.", "👌 Годится. Но если будешь халтурить — пинка получишь!"],
    "praise": ["🥳 Вот теперь молодец! Так держать!", "🚀 Отлично! Возможен бонус."],
    "return_success": ["✅ Вернулся? Работать! Перерыв окончен.", "👍 Теперь давай голосовое, не тяни."],
    "return_demand": ["⏰ 15 минут прошло! Подтверди, что вернулся", "🚨 Перерыв окончен! Где твой голос или сообщение?"],
    "return_demand_hard": ["😡 Ты что, потерялся? Срочно подтверди возврат!", "🤬 Сколько можно ждать?"]
}
duty_call_phrases = ["👀 Кто сегодня за текст ведущего отвечает? Срочно отметься!", "🎤 Кто тут главный? Жду твоего голосового или сообщения!"]
duty_late_phrases = ["😡 Почему не отметился вовремя? Будешь объясняться!", "⏰ 20:30 прошло, а главного не видно! Опоздание — минус к репутации!"]
BREAK_KEYWORDS = ["перерыв", "перекур", "покурить", "обед", "кушать", "ем", "есть", "отдохнуть", "отойти"]
RETURN_CONFIRM_WORDS = ["на месте", "пришел", "пришёл", "покурил", "вернулся", "тут", "готов"]

ACHIEVEMENTS = {
    "perfect_shift": "🏆 Идеальная смена! План по голосовым выполнен на 100%+",
    "stakhanovets": "🔥 Стахановец! Норма перевыполнена в полтора раза!",
    "no_delays": "😇 Точность — вежливость королей! Ни одного опоздания с перерыва."
}

# ========================================
#           ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def get_username(message) -> str:
    if message.from_user.username: return f"@{message.from_user.username}"
    return message.from_user.first_name

def get_user_by_username(users_dict: dict, username: str) -> Tuple[Optional[int], Optional[dict]]:
    for uid, info in users_dict.items():
        if info['username'].lower() == username.lower(): return uid, info
    return None, None

def get_chat_title(chat_id: int) -> str:
    try:
        title = bot.get_chat(chat_id).title
        return title if title else str(chat_id)
    except Exception: return str(chat_id)

def break_requested(text: str) -> bool:
    return any(word in text.lower() for word in BREAK_KEYWORDS)

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

def check_and_award_achievements(chat_id, user_id, user_data):
    perc = round(user_data.get('count', 0) / EXPECTED_VOICES_PER_SHIFT * 100)
    awarded = False
    if perc >= 100 and "perfect_shift" not in user_data["achievements"]:
        user_data["achievements"].add("perfect_shift")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, поздравляю! Ты получаешь достижение:\n_{ACHIEVEMENTS['perfect_shift']}_", parse_mode="Markdown")
        awarded = True
    if perc >= 150 and "stakhanovets" not in user_data["achievements"]:
        user_data["achievements"].add("stakhanovets")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, вот это результат! Новое достижение:\n_{ACHIEVEMENTS['stakhanovets']}_", parse_mode="Markdown")
        awarded = True
    if user_data.get('late_returns', 0) == 0 and "no_delays" not in user_data["achievements"]:
        user_data["achievements"].add("no_delays")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, отличная дисциплина! Достижение:\n_{ACHIEVEMENTS['no_delays']}_", parse_mode="Markdown")
        awarded = True
    return awarded

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
    HELP_TEXT = """<b>Справка по командам:</b>
/start - Назначить себя главным.
/start @username - Назначить главным другого.
/restart - Перезапустить смену.
/статистика - Промежуточный отчет.
/отчет - Финальный отчет.
/рейтинг - Показать рейтинг по голосовым за смену.
/моястатистика - Ваша личная статистика за смену.
/help - Эта справка."""
    bot.send_message(message.chat.id, HELP_TEXT, parse_mode="HTML")

@bot.message_handler(commands=["start", "старт"])
def send_welcome(message):
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    now = datetime.datetime.now(moscow_tz)
    user_id = message.from_user.id
    username = get_username(message)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'main_username': None, 'users': {}, 'shift_start': now, 'chat_title': get_chat_title(chat_id)}
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

# ... (остальные команды: restart, obed, промежуточный, отчет, выгрузка) ...
@bot.message_handler(commands=["restart", "рестарт"])
def restart_main(message):
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    if chat_id in chat_data:
        chat_data[chat_id]['main_id'] = None
        chat_data[chat_id]['main_username'] = None
        chat_data[chat_id]['shift_start'] = datetime.datetime.now(moscow_tz)
        bot.send_message(chat_id, "🔄 Смена перезапущена. Жду нового голосового для назначения главного!")
        save_history_event(message.chat.id, message.from_user.id, get_username(message), "Перезапустил смену")

@bot.message_handler(commands=["промежуточный", "статистика"])
def send_interim_report(message):
    chat_id = message.chat.id
    if chat_id not in chat_data:
        bot.send_message(chat_id, "Нет данных по смене в этом чате.")
        return
    report_lines = get_report_lines(chat_id, chat_data[chat_id])
    bot.send_message(chat_id, "\n".join(report_lines))

@bot.message_handler(commands=["отчет", "otchet"])
def send_manual_admin_report(message):
    send_end_of_shift_reports()
    send_admin_summary()
    bot.reply_to(message, "Отчёт по смене сформирован и отправлен.")

@bot.message_handler(commands=['моястатистика'])
def my_stats(message):
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
    global EXPECTED_VOICES_PER_SHIFT, VOICE_TIMEOUT_MINUTES
    try:
        _, param, value = message.text.split()
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
        bot.reply_to(message, f"Ошибка. Формат: /set <параметр> <значение>\nПример: /set voices 20\n{e}")

# ========================================
#       ОБРАБОТКА СООБЩЕНИЙ И КНОПОК
# ========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    bot.answer_callback_query(callback_query_id=call.id)
    if call.data == "get_stats":
        send_interim_report(call.message)
    elif call.data == "get_report":
        send_manual_admin_report(call.message)
    elif call.data == "get_help":
        show_help(call.message)

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'main_username': None, 'users': {}, 'shift_start': now, 'chat_title': get_chat_title(chat_id)}
    
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
    
    # ... остальная логика handle_voice_message ...
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
    if message.chat.id == ADMIN_CHAT_ID: return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)

    if chat_id not in chat_data or chat_data[chat_id].get('main_id') != user_id:
        bot.reply_to(message, "⛔ Перерыв может взять только текущий главный на смене.")
        return
    user = chat_data[chat_id]['users'][user_id]
    # ... остальная логика перерыва ...
    user.update({
        'breaks_count': user.get('breaks_count', 0) + 1, 'on_break': True,
        'break_start_time': now, 'last_break_time': now, 'waiting_return_confirm': False,
    })
    bot.reply_to(message, random.choice(soviet_phrases["break_acknowledgement"]).format(username=username))

# ... (остальные обработчики и функции отчетов) ...
# ========================================
#           ОТЧЁТЫ И СТАТИСТИКА
# ========================================
def get_report_lines(chat_id, data, full_report=False):
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
        if perc >= 80: praise = "\n" + random.choice(soviet_phrases["praise"])
        elif perc < 50: praise = "\n⚠️ Смена провалена, эфир был слишком тихим!"
        else: praise = ""
        report_lines.append(praise)
    return report_lines

def send_end_of_shift_reports():
    global shift_reports
    shift_reports = []
    
    for chat_id, data in chat_data.items():
        if not data.get('main_id'): continue
        
        main_user_data = data['users'][data['main_id']]
        check_and_award_achievements(chat_id, data['main_id'], main_user_data)
        
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
    if not shift_reports: return
    # ... логика админского отчета ...

# ========================================
#           ПЛАНИРОВЩИК ЗАДАЧ
# ========================================
def check_users_activity():
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in list(chat_data.items()):
        main_id = data.get('main_id')
        if not main_id or main_id not in data.get('users', {}): continue
        user = data['users'][main_id]

        # Проверка таймаута голосовых
        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES and (not user.get('last_remind_time') or (now - user.get('last_remind_time')).total_seconds() / 60 >= REMIND_EACH_MINUTES):
                bot.send_message(chat_id, f"{user['username']}, {random.choice(soviet_phrases['scary_reminder'])}")
                user['last_remind_time'] = now
                # Оповещение админа
                if minutes_passed > VOICE_TIMEOUT_MINUTES + 15:
                     bot.send_message(ADMIN_CHAT_ID, f"⚠️ Алярм! В чате '{get_chat_title(chat_id)}' ведущий {user['username']} молчит уже {int(minutes_passed)} минут!")


def duty_check_late():
    for chat_id, data in chat_data.items():
        if data.get('duty_check_time') and not data.get('duty_confirmed'):
            bot.send_message(chat_id, random.choice(duty_late_phrases))
            # Оповещение админа
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ Внимание! Смена в чате '{get_chat_title(chat_id)}' не началась вовремя.")


def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("04:01", moscow_tz).do(send_end_of_shift_reports)
    # ... остальной планировщик ...

# ========================================
#                ЗАПУСК БОТА
# ========================================
if __name__ == '__main__':
    logging.info("🤖 Бот запущен с новыми функциями...")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
