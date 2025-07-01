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

welcome_phrases = [
    "🎙️ Добро пожаловать, ведущий! Эфир ждет не болтовни, а работы.", "📻 Я тут, чтобы следить за твоей дисциплиной. Готовь голосовые.",
    "🕵️‍♂️ Я контролирую эфир. Не подведи.", "🔔 Теперь за тобой наблюдают. Не расслабляйся.",
    "🎤 Твой голос – твой KPI. Хватит халтуры, работаем!", "🚀 Не забудь: голосовое не будет – премии не будет.",
    "📝 Всё под контролем, каждое слово на счету.", "⏳ Время работает против тебя, если ты молчишь.",
    "😊 Рад тебя видеть. Но руководство ждёт действий.", "😎 Здесь не болото – каждый голос важен!",
    "👋 Если что-то не понял — напиши /help!", "👑 Каждый день — шанс стать лучшим ведущим.",
    "📚 Помни, что /help всегда подскажет команды.", "😼 Сегодня работаешь на результат, не на отмазки.",
    "🙌 Смена только началась — покажи себя!", "🎧 Не забывай — эфир не терпит тишины.",
    "🍀 Желаю удачной смены и продуктивных голосовых!", "💪 Задача на сегодня: максимум активности.",
    "🦾 Ты не один — бот всегда рядом.", "📈 Всё, что ты скажешь, будет учтено в отчёте.",
    "🦉 Внимание! Каждое слово под контролем.", "🦸‍♂️ Герой эфира определяется сегодня!",
    "🎼 Сделай эфир музыкальным — голосовыми!", "🎲 Не играй с удачей, работай на результат.",
    "⚡️ Время перемен начинается с твоего голосового.", "💬 Для всех вопросов и команд используй /help.",
    "👨‍💻 Ты готов? Тогда начнем смену!", "🟢 Все твои действия фиксируются ботом!",
    "📣 Не забывай проявлять инициативу!", "🕰️ Следи за временем — бот напомнит, если что!",
    "🎯 Сегодня твоя задача — быть на высоте.", "👀 Руководство видит все твои успехи.",
    "🥇 Стань лучшим по итогам смены!", "🔋 Зарядись на позитив и вперёд!",
    "🦁 Покажи характер в эфире!", "🌞 С новым днём, с новой сменой!",
    "🌟 Твой успех — это успех команды.", "🔥 Не сдерживай энергию, выложись по полной!",
    "🏆 Начинай смену уверенно!"
]

soviet_phrases = {
    "voice_reminder": [
        "😡 Где голосовое? Пинка получишь сейчас!", "⛔️ Ты что, бессмертный? Голосовое или по жопе!",
        "🚨 В эфире тишина! Давай голосовое, пока не отвезли в лес!", "🕳️ Провалишь смену — объяснять будешь лесорубам.",
        "😤 Эфир не резиновый. Время пошло, текст будет, или тапки?", "💀 Молчание — путь к штрафу. Голосовое — быстро!",
        "🥶 Без твоего текста эфир замерзает. Не дразни судьбу.", "😠 Или ты работаешь, или тебя давно в лес не вывозили?",
        "👿 Следующее напоминание — с ремнем.", "🤬 Руководство на низком старте. Где текст?",
        "📉 Каждый пропуск — минус к премии. Не нарывайся.", "⚠️ Ты опять игноришь эфир? Пинка хочешь?",
        "🚩 Срочно текст ведущего! Или выедешь на природу — без возврата.", "🔥 Или ты оживляешь эфир, или эфир оживит тебя.",
        "📢 Где твой голос? Не позорься, работай!", "😬 Давай, пока не поздно. Голосовое сюда, иначе получишь по пятой точке.",
        "👊 Будет тишина — будет разнос. Не испытывай меня.", "🛑 Голосовое! Не хочешь остаться без штанов?",
        "🗣️ Молчишь? Значит, премии не будет и тапки готовь.", "☠️ Ну что, бездельник, эфир ждёт! Голосовое! Или бегом в лес.",
        "🤡 Думаешь, забуду? У меня память как у начальства.", "😤 Каждый раз, когда ты молчишь, где-то плачет твой кошелёк."
    ],
    "scary_reminder": [
        "👿 Следующее напоминание — с ремнем и выездом в лес.", "🪓 Ты доиграешься, если не пришлёшь голосовое.",
        "💀 Тебя давно не вывозили на природу? Продолжай молчать.", "😈 Жду текст ведущего. Последний шанс, дальше будет больно.",
        "👻 Эфир пустеет. За тобой уже следят.", "⏳ Каждая минута без текста — твоя боль.",
        "🔪 Не доводи до жёстких мер. Я могу быть очень убедительным.", "🩸 Текст ведущего или... жёсткий выговор и объяснительная.",
        "😱 Ты на грани провала смены. Очнись!", "🛑 Последнее предупреждение. Голосовое — сейчас, иначе по жопе.",
        "⚡️ Руководство уже в курсе твоей бездеятельности."
    ],
    "break_acknowledgement": [
        "☕ Перерыв засчитан, {username}. Смотри, чтобы не затянулся.", "🍔 Быстро перекуси и назад работать.",
        "🕰️ 15 минут и не секундой больше.", "🍵 Перерыв, но не расслабляйся.",
        "🥨 Через 15 минут жду голосовое.", "🍫 Не забудь вернуться вовремя.",
        "🧃 Отдыхай, но премию за опоздание не жди.", "🥯 Всё под контролем. Перерыв пошёл.",
        "🥤 Потом снова за работу.", "🕑 Помни, что время идёт."
    ],
    "break_too_soon": [
        "❌ Не наглей! Перерыв только раз в час. Терпи ещё {minutes} мин. Не раскисай!",
        "🕐 Ты недавно отдыхал. Ещё рано, работай! До следующего перерыва {minutes} мин.",
        "⏳ Перерыв не раньше чем через {minutes} мин. Терпи, эфир не любит слабаков.",
        "💢 Ты только что оторвал пятую точку от стула. Подожди ещё {minutes} мин.",
        "🥊 Перерыв раз в час! Осталось {minutes} мин. Держись, не разваливайся."
    ],
    "too_short": [
        "🗑️ Ты это сейчас всерьёз? Голосовое меньше 7 секунд — даже читать стыдно.",
        "⏳ Такой короткий текст даже ёжик бы не принял.", "😤 Меньше 7 секунд — не считается! Не халтурь.",
        "👎 Это не голосовое, а микро-пердеж. Перезапиши!", "🙄 Если не можешь наговорить хотя бы 7 секунд — зачем ты здесь?",
        "⚠️ Это не голосовое, это издевательство."
    ],
    "accept": [
        "✅ Принято. Следи за сменой, не расслабляйся.", "👌 Годится. Но если будешь халтурить — пинка получишь!",
        "👍 Отметил. Ещё пару таких — и, может быть, не уволю.", "🚩 Зафиксировал. Но если голосовых мало — выезжаем в лес.",
        "😏 Принято, но расслабляться рано. Я за тобой слежу!", "🦾 Так держать. Но отдыхать будешь только после смены.",
        "👀 Принял. За каждым твоим словом — мой зоркий глаз.", "😈 Пока хорошо, но попробуй только замолчать.",
        "📝 Записал. Но если план не сделаешь — сам знаешь что будет."
    ],
    "praise": [
        "🥳 Вот теперь молодец! Так держать!", "🚀 Отлично! Возможен бонус.",
        "🔥 Вот теперь руководство довольно.", "🌟 Такими темпами и до премии недалеко.",
        "🎉 Вот это результат! Бери пример с себя.", "💪 Идеальная смена — так и надо.",
        "🍀 Не расслабляйся, держи темп.", "😉 Руководство увидело, что ты можешь."
    ],
    "return_success": [
        "✅ Вернулся? Работать! Перерыв окончен.", "👍 Теперь давай голосовое, не тяни.",
        "👏 Время снова доказывать свою полезность.", "🎩 Перерыв закончился — эфир ждёт.",
        "🕺 Быстро в строй, {username}!", "🏅 Теперь без оправданий, работаем.",
        "🎯 Эфир не ждёт — пора в бой.", "🌞 Жду текст ведущего, не расслабляйся.",
        "🛠️ Перерыв был, теперь за работу.", "🚦 Работать, работать и ещё раз работать."
    ],
    "return_demand": [
        "⏰ 15 минут прошло! Подтверди, что вернулся: напиши 'Я на месте', 'пришёл' и т.п. или пришли голосовое!",
        "🚨 Перерыв окончен! Где твой голос или сообщение? Отметься!", "🕰️ Всё, отдых закончен. Напиши 'на месте' или пришли голосовое!",
        "👀 Я жду подтверждения возврата! Не тяни, эфир ждёт.", "🔥 Перерыв завершён! Срочно отметься в чате."
    ],
    "return_demand_hard": [
        "😡 Ты что, потерялся? Срочно подтверди возврат!", "🤬 Сколько можно ждать? Жду 'я на месте' или голосовое!",
        "😈 Не вынуждай повторять — отметься немедленно!", "🚨 Второй раз зову! Эфир не ждёт бездельников!",
        "👹 Если не отметишься — выговор обеспечен!"
    ]
}

duty_call_phrases = [
    "👀 Кто сегодня за текст ведущего отвечает? Срочно отметься!", "🎤 Кто тут главный? Жду твоего голосового или сообщения!",
    "📣 Эй! Кто сегодня командует эфиром? Не молчать!", "⏰ 20:00! Кто отвечает за текст ведущего? Быстро в чат!",
    "🕵️‍♂️ Где главный смены? Не прячься, покажи себя!", "🚨 Кто несёт ответственность за эфир? Голосовое — сюда!",
    "🦾 Кто сегодня держит эфир в тонусе? Жду отклика!", "👋 Кто главный? Молчание — не вариант!"
]
duty_late_phrases = [
    "😡 Почему не отметился вовремя? Будешь объясняться!", "⏰ 20:30 прошло, а главного не видно! Опоздание — минус к репутации!",
    "🛑 Опять проспал? В следующий раз будь оперативней!", "😤 Не успел вовремя? За это можно и по жопе получить.",
    "🚨 Смена без ответственного — сразу провал! Где ты был?", "😱 До последнего тянул? Так дело не пойдёт!"
]

BREAK_KEYWORDS = [
    "перерыв", "перекур", "покурить", "я на перерыв", "я на обед", "обед", "я кушать",
    "кушать", "ем", "есть", "отдохнуть", "пить", "кофе", "чай", "отойти", "отойду"
]

RETURN_CONFIRM_WORDS = [
    "на месте", "пришел", "пришёл", "покурил", "вернулся", "тут", "готов", "я тут"
]

ACHIEVEMENTS = {
    "perfect_shift": "🏆 Идеальная смена! План по голосовым выполнен на 100%+",
    "stakhanovets": "🔥 Стахановец! Норма перевыполнена в полтора раза!",
    "no_delays": "😇 Точность — вежливость королей! Ни одного опоздания с перерыва."
}

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
    
    # Достижение: Идеальная смена
    if perc >= 100 and "perfect_shift" not in user_data["achievements"]:
        user_data["achievements"].add("perfect_shift")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, поздравляю! Ты получаешь достижение:\n_{ACHIEVEMENTS['perfect_shift']}_", parse_mode="Markdown")

    # Достижение: Стахановец
    if perc >= 150 and "stakhanovets" not in user_data["achievements"]:
        user_data["achievements"].add("stakhanovets")
        bot.send_message(chat_id, f"🎉 {user_data['username']}, вот это результат! Новое достижение:\n_{ACHIEVEMENTS['stakhanovets']}_", parse_mode="Markdown")

    # Достижение: Без опозданий
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
        # Сортируем пользователей по количеству голосовых
        sorted_users = sorted(users.items(), key=lambda item: item[1]['count'], reverse=True)
        
        rating_text = "🏆 Рейтинг по голосовым за текущую смену:\n\n"
        for i, (uid, udata) in enumerate(sorted_users[:10], 1): # Показываем топ-10
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
        if perc >= 80: praise = "\n" + random.choice(soviet_phrases["praise"])
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
    # ... логика админского отчета (остается без изменений)

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
        
        # Проверка возврата с перерыва
        if user.get('on_break'):
            minutes_on_break = (now - user['break_start_time']).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES and not user.get('waiting_return_confirm'):
                bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['return_demand'])}")
                user.update({'waiting_return_confirm': True, 'remind_return_time': now})
                save_history_event(chat_id, main_id, username, "Отправлено напоминание о возврате с перерыва")
            continue

        # Повторное напоминание о возврате
        if user.get('waiting_return_confirm'):
            remind_time = user.get('remind_return_time')
            if remind_time and (now - remind_time).total_seconds() / 60 > WAIT_RETURN_CONFIRM_MINUTES:
                bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['return_demand_hard'])}")
                user['remind_return_time'] = now
            continue

        # Проверка активности (голосовые)
        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES:
                last_remind = user.get('last_remind_time')
                if not last_remind or (now - last_remind).total_seconds() / 60 >= REMIND_EACH_MINUTES:
                    bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['scary_reminder'])}")
                    user['last_remind_time'] = now
                    save_history_event(chat_id, main_id, username, "Отправлено напоминание о голосовом")
                    # Уведомление для админа о длительном простое
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
    logging.info("🤖 Бот запущен с новыми функциями...")
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logging.error(f"Критическая ошибка polling: {e}")
            time.sleep(15)
```
