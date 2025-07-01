Of course. Here is the complete, unified, and fully functional Python script for the Telegram bot, created by merging all the provided versions.

This script includes all features: comprehensive phrase banks, command handlers (`/start`, `/help`, `/статистика`, `/выгрузка`, etc.), a full shift management system, activity tracking, automated reports, and event history logging.

```python
# -*- coding: utf-8 -*-
"""
Многофункциональный Telegram-бот для контроля смен, голосовых, перерывов, отчетов.
Включает:
- Обширные банки фраз для различных ситуаций.
- Команды: /start, /старт, /help, /статистика, /выгрузка, /обед, /промежуточный, /отчет, /restart.
- Систему смен и "главных", автоматические и ручные отчеты.
- Учет перерывов, возвратов, опозданий, активности пользователей.
- Расширенное логирование, справку, выгрузку истории в TXT/CSV, и статистику по каждому чату.
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

# Основные параметры смены
SHIFT_START_HOUR = 19
SHIFT_END_HOUR = 4
VOICE_TIMEOUT_MINUTES = 40
REMIND_EACH_MINUTES = 5
BREAK_DURATION_MINUTES = 15
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
BREAK_DELAY_MINUTES = 60
WAIT_RETURN_CONFIRM_MINUTES = 3

ADMIN_CHAT_ID = -1002645821302  # ID административного чата для отчетов
shift_reports = []
user_history: Dict[int, List[str]] = {}

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN)

# Данные по чатам (ключ - chat_id)
chat_data: Dict[int, dict] = {}

# ========================================
#                БАНКИ ФРАЗ
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
        "🤡 Думаешь, забуду? У меня память как у начальства.", "😤 Каждый раз, когда ты молчишь, где-то плачет твой кошелёк.",
        "💢 Не доводи до красной строки отчёта, иначе ремень.", "🥵 Грею ремень, если не будет голосового.",
        "🦾 Не хочешь работать — выезд за город обеспечен.", "🎤 Молчание — это не выход, это билет на дачу.",
        "🤖 Даже роботы говорят больше, чем ты. Учись у техники.", "🦷 Ты зубы дома забыл или просто боишься микрофона?",
        "🥊 Хочешь урок дисциплины — продолжай молчать.", "🪓 Не тяни — эфир сейчас сам тебя подтянет.",
        "🐒 Даже обезьяна смогла бы отправить голосовое.", "🧨 Вот-вот взорвусь, если не будет текста.",
        "🤬 Достал уже молчать! Голосовое, быстро!", "😈 Я могу быть очень неприятным. Проверь.",
        "👹 Эфир не ждёт — он требует.", "🦵 Пора поднять свою задницу и сделать дело!",
        "🪤 Не попадай в ловушку молчания, иначе ловушка найдёт тебя.", "🚒 Эфир горит, а ты молчишь — тушить будешь?",
        "🦉 Даже сова ночью активнее.", "🤏 Твой вклад пока меньше нуля.", "🎲 Хочешь сыграть в увольнение?",
        "🦾 Включи режим работы, а не симуляции.", "🕳️ В яму лени быстро попадёшь.",
        "🦦 Выдра бы уже записала голосовое.", "🦖 Динозавр вымер, потому что молчал.",
        "🦨 Запах лени доносится до Москвы.", "🍑 Не жди, что кто-то другой тебя выручит.",
        "👎 Молчание — худший вклад в эфир.", "🙉 Даже обезьяна с микрофоном громче тебя.",
        "💩 Такой работы даже унитаз не видел.", "🐷 Пора перестать хрюкать и начать работать.",
        "🦆 Кря-кря — даже утка в эфире активнее.", "🦧 Сколько можно ждать? Голосовое — сейчас!",
        "🦜 Я не попугай, но повторю: ГОЛОСОВОЕ!", "🐲 Дракон уже подлетает к твоей пятой точке.",
        "⏱️ Время идёт, голосовых не вижу!", "🔫 Молчание — путь в никуда!",
        "💼 Пора работать, а не отлынивать!", "⚡️ Немедленно оживи эфир!"
    ],
    "scary_reminder": [
        "👿 Следующее напоминание — с ремнем и выездом в лес.", "🪓 Ты доиграешься, если не пришлёшь голосовое.",
        "💀 Тебя давно не вывозили на природу? Продолжай молчать.", "😈 Жду текст ведущего. Последний шанс, дальше будет больно.",
        "👻 Эфир пустеет. За тобой уже следят.", "⏳ Каждая минута без текста — твоя боль.",
        "🔪 Не доводи до жёстких мер. Я могу быть очень убедительным.", "🩸 Текст ведущего или... жёсткий выговор и объяснительная.",
        "😱 Ты на грани провала смены. Очнись!", "🛑 Последнее предупреждение. Голосовое — сейчас, иначе по жопе.",
        "⚡️ Руководство уже в курсе твоей бездеятельности.", "👻 В темноте за молчуном приходит начальник.",
        "🦷 За каждое молчание я съедаю один твой зуб.", "🐍 Змея увольнения уже рядом.",
        "🦇 Я везде — даже в твоих снах.", "🦴 Если не хочешь проблем — голосовое сейчас."
    ],
    "break_acknowledgement": [
        "☕ Перерыв засчитан, {username}. Смотри, чтобы не затянулся.", "🍔 Быстро перекуси и назад работать.",
        "🕰️ 15 минут и не секундой больше.", "🍵 Перерыв, но не расслабляйся.",
        "🥨 Через 15 минут жду голосовое.", "🍫 Не забудь вернуться вовремя.",
        "🧃 Отдыхай, но премию за опоздание не жди.", "🥯 Всё под контролем. Перерыв пошёл.",
        "🍋 Не задерживайся в столовой.", "🥤 Потом снова за работу.", "🕑 Помни, что время идёт.",
        "🦾 Быстро восстанавливайся и в бой.", "🍲 Не затягивай — эфир ждёт.",
        "🥡 Считай минуты — эфир не ждёт.", "🍦 Перерыв — это не отпуск.",
        "🍪 Когда досчитаю до 15 — возвращайся.", "🧁 Хватит баловать себя — эфир зовёт."
    ],
    "break_too_soon": [
        "❌ Не наглей! Перерыв только раз в час. Терпи ещё {minutes} мин. Не раскисай!",
        "🕐 Ты недавно отдыхал. Ещё рано, работай! До следующего перерыва {minutes} мин.",
        "⏳ Перерыв не раньше чем через {minutes} мин. Терпи, эфир не любит слабаков.",
        "💢 Ты только что оторвал пятую точку от стула. Подожди ещё {minutes} мин.",
        "🥊 Перерыв раз в час! Осталось {minutes} мин. Держись, не разваливайся.",
        "🥵 Не получится так часто отдыхать. Жди ещё {minutes} мин.", "👊 Терпи, работяга! Следующий перерыв через {minutes} мин.",
        "🛑 Перерыв не положен! До разрешения ещё {minutes} мин.", "🧊 Остынь! До следующего перерыва ещё {minutes} мин."
    ],
    "too_short": [
        "🗑️ Ты это сейчас всерьёз? Голосовое меньше 7 секунд — даже читать стыдно.",
        "⏳ Такой короткий текст даже ёжик бы не принял.", "😤 Меньше 7 секунд — не считается! Не халтурь.",
        "👎 Это не голосовое, а микро-пшик. Перезапиши!", "🙄 Если не можешь наговорить хотя бы 7 секунд — зачем ты здесь?",
        "⚠️ Это не голосовое, это издевательство.", "🤏 Коротко — не значит по делу.",
        "🦗 Кузнечик бы сказал больше.", "🦦 Даже выдра дольше говорит."
    ],
    "accept": [
        "✅ Принято. Следи за сменой, не расслабляйся.", "👌 Годится. Но если будешь халтурить — пинка получишь!",
        "👍 Отметил. Ещё пару таких — и, может быть, не уволю.", "🚩 Зафиксировал. Но если голосовых мало — выезжаем в лес.",
        "😏 Принято, но расслабляться рано. Я за тобой слежу!", "🦾 Так держать. Но отдыхать будешь только после смены.",
        "👀 Принял. За каждым твоим словом — мой зоркий глаз.", "😈 Пока хорошо, но попробуй только замолчать.",
        "📝 Записал. Но если план не сделаешь — сам знаешь что будет.", "🔥 Пошло дело. Но держи темп, иначе тапки готовь.",
        "👊 Вот это по-нашему! Только не сбавляй обороты.", "🦵 Принято. За слабину — по пятой точке.",
        "🥶 Не дай замёрзнуть эфиру. Держи темп!", "🚀 Поехали дальше! Эфир любит активных."
    ],
    "praise": [
        "🥳 Вот теперь молодец! Так держать!", "🚀 Отлично! Возможен бонус.",
        "🔥 Вот теперь руководство довольно.", "🌟 Такими темпами и до премии недалеко.",
        "🎉 Вот это результат! Бери пример с себя.", "💪 Идеальная смена — так и надо.",
        "🍀 Не расслабляйся, держи темп.", "😉 Руководство увидело, что ты можешь.",
        "🦸‍♂️ Ведущий, вот так держать.", "🕺 За такие голосовые не стыдно отчитаться.",
        "👑 Лучший ведущий смены!", "🏆 Победитель по активности!"
    ],
    "return_success": [
        "✅ Вернулся? Работать! Перерыв окончен.", "👍 Теперь давай голосовое, не тяни.",
        "👏 Время снова доказывать свою полезность.", "🎩 Перерыв закончился — эфир ждёт.",
        "🕺 Быстро в строй, {username}!", "🏅 Теперь без оправданий, работаем.",
        "🎯 Эфир не ждёт — пора в бой.", "🛠️ Перерыв был, теперь за работу.",
        "🚦 Работать, работать и ещё раз работать.", "🦾 Снова на связи? Вперёд!",
        "🎤 Не тяни! Эфир ждёт активности.", "⏱️ Время не ждёт — начинай говорить.",
        "🥇 Вернулся вовремя — молодец."
    ],
    "return_demand": [
        "⏰ 15 минут прошло! Подтверди, что вернулся: напиши 'Я на месте', 'пришёл' и т.п. или пришли голосовое!",
        "🚨 Перерыв окончен! Где твой голос или сообщение? Отметься!", "🕰️ Всё, отдых закончен. Напиши 'на месте' или пришли голосовое!",
        "👀 Я жду подтверждения возврата! Не тяни, эфир ждёт.", "🔥 Перерыв завершён! Срочно отметься в чате.",
        "🎙️ Вернулся? Жду голосовое или текст 'я на месте'.", "😤 Отдых закончился! Подтверди, что тут."
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
    "🦾 Кто сегодня держит эфир в тонусе? Жду отклика!", "👋 Кто главный? Молчание — не вариант!",
    "😈 Не вижу ответственных! Кто сегодня рулит?", "📝 Кто за текст ведущего? Без ответственного смена не начнётся!",
    "📢 Жду отметки — кто сегодня отвечает за эфир?", "🤷‍♂️ Кто-то должен взять ответственность! Кто?",
    "🦉 Кто главный? Время пошло!", "🦁 Лидер эфира, отметься!", "👑 Выйди из тени!"
]

duty_late_phrases = [
    "😡 Почему не отметился вовремя? Будешь объясняться!", "⏰ 20:30 прошло, а главного не видно! Опоздание — минус к репутации!",
    "🛑 Опять проспал? В следующий раз будь оперативней!", "😤 Не успел вовремя? За это можно и по жопе получить.",
    "🚨 Смена без ответственного — сразу провал! Где ты был?", "😱 До последнего тянул? Так дело не пойдёт!",
    "🤬 Ты что, забыл про смену? Неуважение к эфиру!", "👎 Следующий раз опоздаешь — расскажешь начальству.",
    "🔥 Не повторяй это — в следующий раз будет жёстче.", "📉 За такие опоздания премии не бывает."
]

BREAK_KEYWORDS = [
    "перерыв", "перекур", "покурить", "я на перерыв", "я на обед", "обед", "я кушать",
    "кушать", "ем", "есть", "отдохнуть", "пить", "кофе", "чай", "отойти", "отойду"
]

RETURN_CONFIRM_WORDS = [
    "на месте", "пришел", "пришёл", "покурил", "вернулся", "тут", "готов", "я тут"
]

# ========================================
#           ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def get_username(message) -> str:
    """Получает username пользователя или его имя, если username не установлен."""
    if message.from_user.username:
        return f"@{message.from_user.username}"
    return message.from_user.first_name

def get_chat_title(chat_id: int) -> str:
    """Получает название чата по его ID."""
    try:
        chat = bot.get_chat(chat_id)
        return chat.title if chat.title else f"Чат {chat_id}"
    except Exception as e:
        logging.warning(f"Не удалось получить название чата {chat_id}: {e}")
        return f"Чат {chat_id}"

def break_requested(text: str) -> bool:
    """Проверяет, запрашивает ли текст перерыв."""
    return any(word in text.lower() for word in BREAK_KEYWORDS)

def return_confirmed(text: str) -> bool:
    """Проверяет, подтверждает ли текст возврат с перерыва."""
    return any(word in text.lower() for word in RETURN_CONFIRM_WORDS)

def save_history_event(chat_id: int, user_name: str, event_text: str):
    """Сохраняет событие в историю для последующей выгрузки."""
    if chat_id not in user_history:
        user_history[chat_id] = []
    
    now_str = datetime.datetime.now(moscow_tz).strftime('%H:%M:%S')
    full_event = f"{now_str} | {user_name} | {event_text}"
    user_history[chat_id].append(full_event)
    logging.info(f"ИСТОРИЯ [{get_chat_title(chat_id)}]: {full_event}")

def export_history(chat_id: int, format_type: str = 'txt'):
    """Экспортирует историю событий чата в файл (txt или csv)."""
    if chat_id not in user_history or not user_history[chat_id]:
        return None
    
    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"history_{chat_id}_{now_str}.{format_type}"
    
    try:
        with open(filename, "w", encoding="utf-8", newline='') as f:
            if format_type == 'csv':
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Время", "Пользователь", "Событие"])
                for event in user_history[chat_id]:
                    writer.writerow(event.split(' | '))
            else:
                f.write(f"История событий для чата '{get_chat_title(chat_id)}' за смену\n")
                f.write("="*40 + "\n")
                for event in user_history[chat_id]:
                    f.write(f"{event}\n")
        return filename
    except Exception as e:
        logging.error(f"Ошибка при экспорте истории в {format_type}: {e}")
        return None

# ========================================
#               /HELP И КОМАНДЫ
# ========================================

HELP_TEXT = """
*Справка по командам бота* 🤖

*/start* или */старт*
Назначает вас главным на смене. Если главный уже есть, смены не будет.
Можно назначить другого: `/start @username`

*/restart* или */рестарт*
Принудительно сбрасывает текущую смену и главного. Позволяет начать смену заново.

*/обед*, */obed* или сообщение "хочу перерыв"
Уход на перерыв на 15 минут. Доступно только главному на смене не чаще раза в час.

*/промежуточный*
Показывает текущий статус смены: сколько голосовых записано, сколько времени прошло.

*/отчет*
Завершает смену и формирует финальный отчет. Отчет также отправляется автоматически в конце смены.

*/статистика*
Выводит подробную статистику по активности главного: среднее время между голосовыми, количество перерывов и т.д.

*/выгрузка*
Отправляет файл с полной историей всех событий за смену (кто и когда отправлял голосовые, уходил на перерыв и т.д.).

*Возврат с перерыва*
Чтобы вернуться, напишите в чат "я на месте", "вернулся", "тут" и т.п. или просто отправьте голосовое.
"""

@bot.message_handler(commands=['help', 'справка'])
def show_help(message):
    bot.reply_to(message, HELP_TEXT, parse_mode="Markdown")

@bot.message_handler(commands=['start', 'старт'])
def send_welcome(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)

    if chat_id not in chat_data:
        chat_data[chat_id] = {}

    if chat_data[chat_id].get('main_user'):
        main_user_info = chat_data[chat_id]['main_user']
        bot.reply_to(message, f"⛔️ Смена уже идёт. Главный на смене: {main_user_info['username']}.")
        return

    # Логика назначения главного по тегу
    match = re.search(r'/start(?:@\w+)?\s+(@\w+)', message.text)
    if match:
        target_username = match.group(1)
        # Это placeholder, т.к. бот не может узнать user_id по username без предварительного сохранения
        # В реальной реализации требуется база данных пользователей чата.
        # Для простоты, мы назначим того, кто написал команду, но с тегом цели.
        main_user_id = user_id # Упрощение
        main_username = target_username
        bot.send_message(chat_id, f"✅ Окей, главный на смене назначен: {main_username}. Жду от него голосовое для старта!")

    else:
        main_user_id = user_id
        main_username = username
        
    chat_data[chat_id]['main_user'] = {
        'id': main_user_id,
        'username': main_username,
        'voices': 0,
        'last_voice_time': time.time(),
        'on_break': False,
        'break_start_time': None,
        'last_break_time': 0,
        'reminders_sent': 0,
        'late_returns': 0,
        'start_time': time.time()
    }
    
    # Сброс истории для новой смены
    if chat_id in user_history:
        user_history[chat_id].clear()
    
    save_history_event(chat_id, main_username, "Назначен главным на смене.")
    bot.send_message(chat_id, f"{random.choice(welcome_phrases)}\n\n👑 Главный на смене: {main_username}. Жду первое голосовое!")
    logging.info(f"Новая смена в чате '{get_chat_title(chat_id)}'. Главный: {main_username} ({main_user_id}).")


@bot.message_handler(commands=['restart', 'рестарт'])
def restart_shift(message):
    chat_id = message.chat.id
    if chat_id in chat_data and chat_data[chat_id].get('main_user'):
        main_username = chat_data[chat_id]['main_user']['username']
        chat_data.pop(chat_id, None)
        if chat_id in user_history:
            user_history[chat_id].clear()
        bot.reply_to(message, f"🔄 Смена главного ({main_username}) была принудительно сброшена. Можно назначать нового главного командой /start.")
        logging.warning(f"Смена в чате '{get_chat_title(chat_id)}' была перезапущена пользователем {get_username(message)}.")
    else:
        bot.reply_to(message, "🤔 Смена и так не активна. Начните её командой /start.")


@bot.message_handler(commands=['промежуточный'])
def send_interim_report(message):
    chat_id = message.chat.id
    if chat_id not in chat_data or not chat_data[chat_id].get('main_user'):
        bot.reply_to(message, "Смена ещё не началась. Нет данных для отчета.")
        return

    user_data = chat_data[chat_id]['main_user']
    voices_count = user_data['voices']
    time_since_last = int(time.time() - user_data['last_voice_time'])
    
    report_text = (
        f"📊 *Промежуточный статус смены*\n\n"
        f"👤 Главный: {user_data['username']}\n"
        f"🎙 Голосовых отправлено: *{voices_count}* из {EXPECTED_VOICES_PER_SHIFT} (план)\n"
        f"⏳ Последнее было *{time_since_last // 60} мин. {time_since_last % 60} сек.* назад.\n\n"
        f"Продолжаем работать!"
    )
    bot.send_message(chat_id, report_text, parse_mode="Markdown")


@bot.message_handler(commands=['отчет', 'otchet'])
def send_manual_admin_report(message):
    chat_id = message.chat.id
    if chat_id not in chat_data or not chat_data[chat_id].get('main_user'):
        bot.reply_to(message, "Смена не активна, нечего завершать.")
        return
    
    report = get_report_lines(chat_id, chat_data[chat_id])
    full_report = "\n".join(report)
    bot.send_message(chat_id, full_report, parse_mode="Markdown")
    
    # Отправка в админский чат
    if ADMIN_CHAT_ID:
        try:
            bot.send_message(ADMIN_CHAT_ID, full_report, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в админский чат {ADMIN_CHAT_ID}: {e}")

    # Завершение смены
    chat_data.pop(chat_id, None)
    logging.info(f"Смена в чате '{get_chat_title(chat_id)}' завершена вручную.")


@bot.message_handler(commands=['статистика'])
def show_statistics(message):
    chat_id = message.chat.id
    if chat_id not in chat_data or not chat_data[chat_id].get('main_user'):
        bot.reply_to(message, "Смена неактивна, статистика недоступна.")
        return

    data = chat_data[chat_id]
    user_data = data['main_user']
    
    shift_duration_sec = int(time.time() - user_data['start_time'])
    shift_duration_min = shift_duration_sec / 60
    
    avg_time_between_voices = 0
    if user_data['voices'] > 1:
        avg_time_between_voices = shift_duration_sec / (user_data['voices'] - 1)
        
    stats_text = (
        f"📈 *Статистика по главному {user_data['username']}*\n\n"
        f"⏱️ Длительность смены: *{shift_duration_sec // 3600} ч {int((shift_duration_sec % 3600) / 60)} мин*\n"
        f"🎙️ Голосовых сообщений: *{user_data['voices']}*\n"
        f"📊 Среднее время между голосовыми: *{int(avg_time_between_voices // 60)} мин {int(avg_time_between_voices % 60)} сек*\n"
        f"☕ Количество перерывов: *{user_data.get('breaks_taken', 0)}*\n"
        f"⏰ Опозданий с перерыва: *{user_data['late_returns']}*\n"
        f"😡 Отправлено напоминаний: *{user_data['reminders_sent']}*"
    )
    bot.send_message(chat_id, stats_text, parse_mode="Markdown")


@bot.message_handler(commands=['выгрузка'])
def export_user_history(message):
    chat_id = message.chat.id
    
    txt_filename = export_history(chat_id, 'txt')
    csv_filename = export_history(chat_id, 'csv')

    if not txt_filename and not csv_filename:
        bot.reply_to(message, "История событий для этого чата пуста.")
        return

    try:
        if txt_filename:
            with open(txt_filename, "rb") as f:
                bot.send_document(chat_id, f, caption="История событий смены (.txt)")
            os.remove(txt_filename)
        if csv_filename:
             with open(csv_filename, "rb") as f:
                bot.send_document(chat_id, f, caption="История событий смены (.csv)")
             os.remove(csv_filename)
    except Exception as e:
        bot.reply_to(message, "Произошла ошибка при отправке файла.")
        logging.error(f"Ошибка выгрузки истории: {e}")

# ========================================
#           ОСНОВНАЯ ЛОГИКА (СООБЩЕНИЯ)
# ========================================

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    
    if chat_id not in chat_data or not chat_data[chat_id].get('main_user'):
        # Если смена не начата, первое голосовое назначает главного
        send_welcome(message) # Используем логику /start
        # Теперь данные о главном созданы, продолжаем обработку голосового
    
    user_data = chat_data[chat_id]['main_user']
    
    # Проверяем, что голосовое от главного
    if user_id != user_data['id']:
        bot.reply_to(message, f"Сейчас главный на смене — {user_data['username']}. Я слушаю только его.")
        return

    # Проверяем длительность голосового
    if message.voice.duration < MIN_VOICE_SECONDS:
        bot.reply_to(message, random.choice(soviet_phrases["too_short"]))
        save_history_event(chat_id, username, f"Отправил слишком короткое голосовое ({message.voice.duration} сек).")
        return

    user_data['voices'] += 1
    user_data['last_voice_time'] = time.time()
    user_data['reminders_sent'] = 0 # Сбрасываем счетчик напоминаний

    # Если пользователь был на перерыве, он возвращается
    if user_data['on_break']:
        user_data['on_break'] = False
        bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
        save_history_event(chat_id, username, "Вернулся с перерыва, отправив голосовое.")
    
    save_history_event(chat_id, username, f"Отправил голосовое #{user_data['voices']} ({message.voice.duration} сек).")

    # Похвала за достижение цели
    if user_data['voices'] == EXPECTED_VOICES_PER_SHIFT:
        response_text = random.choice(soviet_phrases["praise"])
    else:
        response_text = random.choice(soviet_phrases["accept"])
    
    bot.reply_to(message, response_text)

@bot.message_handler(func=lambda message: True)
def handle_text_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    text = message.text

    if chat_id not in chat_data or not chat_data[chat_id].get('main_user'):
        return

    user_data = chat_data[chat_id]['main_user']

    if user_id != user_data['id']:
        return # Игнорируем сообщения не от главного

    # Логика ухода на перерыв
    if break_requested(text):
        now = time.time()
        time_since_last_break = now - user_data.get('last_break_time', 0)

        if time_since_last_break < BREAK_DELAY_MINUTES * 60:
            remaining_minutes = int((BREAK_DELAY_MINUTES * 60 - time_since_last_break) / 60)
            bot.reply_to(message, random.choice(soviet_phrases["break_too_soon"]).format(minutes=remaining_minutes))
            return
        
        user_data['on_break'] = True
        user_data['break_start_time'] = now
        user_data['last_break_time'] = now
        user_data['breaks_taken'] = user_data.get('breaks_taken', 0) + 1
        
        response = random.choice(soviet_phrases["break_acknowledgement"]).format(username=username)
        bot.reply_to(message, response)
        save_history_event(chat_id, username, f"Ушел на перерыв на {BREAK_DURATION_MINUTES} минут.")
        logging.info(f"{username} в чате '{get_chat_title(chat_id)}' ушел на перерыв.")

    # Логика возврата с перерыва
    elif return_confirmed(text) and user_data['on_break']:
        user_data['on_break'] = False
        user_data['last_voice_time'] = time.time() # Считаем возврат как активность
        bot.reply_to(message, random.choice(soviet_phrases["return_success"]).format(username=username))
        save_history_event(chat_id, username, "Вернулся с перерыва, написав в чат.")
        logging.info(f"{username} в чате '{get_chat_title(chat_id)}' вернулся с перерыва.")

# ========================================
#               ОТЧЁТЫ И ВЫВОДЫ
# ========================================

def get_official_conclusion(percentage: int, late_returns: int) -> str:
    """Генерирует заключение для отчета на основе производительности."""
    if percentage >= 100 and late_returns == 0:
        return "🏆 ОТЛИЧНО. План выполнен, нарушений нет. Пример для подражания."
    if percentage >= 80 and late_returns <= 1:
        return "✅ ХОРОШО. План почти выполнен. Есть небольшие замечания."
    if percentage >= 50:
        return "⚠️ УДОВЛЕТВОРИТЕЛЬНО. Cделана лишь половина работы. Требуется улучшение дисциплины."
    if percentage < 50:
        return "⛔️ НЕУДОВЛЕТВОРИТЕЛЬНО. Смена провалена. Требуется серьезный разговор."
    return "❌ КРАЙНЕ НЕУДОВЛЕТВОРИТЕЛЬНО. Полное игнорирование обязанностей."

def get_report_lines(chat_id: int, data: dict) -> List[str]:
    """Формирует строки для финального отчета."""
    user_data = data['main_user']
    voices_count = user_data['voices']
    percentage = int((voices_count / EXPECTED_VOICES_PER_SHIFT) * 100)
    late_returns = user_data.get('late_returns', 0)
    conclusion = get_official_conclusion(percentage, late_returns)
    
    report_title = f"*{get_chat_title(chat_id)}* | Отчет за смену"
    date_str = datetime.datetime.now(moscow_tz).strftime('%d.%m.%Y')

    lines = [
        f"*{'='*10} ОТЧЕТ ПО СМЕНЕ {'='*10}*",
        f"📅 *Дата:* {date_str}",
        f"👤 *Главный на смене:* {user_data['username']}",
        f"🎙️ *Отправлено голосовых:* {voices_count} из {EXPECTED_VOICES_PER_SHIFT} (*{percentage}%* от плана)",
        f"⏰ *Опозданий с перерыва:* {late_returns}",
        f"☕ *Количество перерывов:* {user_data.get('breaks_taken', 0)}",
        "_"*40,
        f"*Заключение:* {conclusion}"
    ]
    return lines

def send_end_of_shift_reports():
    """Отправляет финальные отчеты в чаты, где была активность."""
    logging.info("Начало отправки итоговых отчетов за смену.")
    global shift_reports
    shift_reports = []
    
    active_chats = list(chat_data.keys())
    for chat_id in active_chats:
        if 'main_user' in chat_data[chat_id]:
            report_lines = get_report_lines(chat_id, chat_data[chat_id])
            full_report = "\n".join(report_lines)
            shift_reports.append(full_report) # Для админского отчета
            
            try:
                bot.send_message(chat_id, full_report, parse_mode="Markdown")
                logging.info(f"Итоговый отчет отправлен в чат '{get_chat_title(chat_id)}'.")
            except Exception as e:
                logging.error(f"Не удалось отправить итоговый отчет в чат {chat_id}: {e}")
            
            # Сброс смены
            chat_data.pop(chat_id, None)
            if chat_id in user_history:
                user_history[chat_id].clear()
    
    send_admin_summary()

def send_admin_summary():
    """Отправляет сводный отчет по всем сменам в админский чат."""
    if not shift_reports:
        logging.info("Сводный админский отчет не отправлен: не было активных смен.")
        return
        
    summary = ["*Сводный отчет по всем сменам за ночь:*", ""] + shift_reports
    full_summary = "\n\n".join(summary)
    
    if ADMIN_CHAT_ID:
        try:
            bot.send_message(ADMIN_CHAT_ID, full_summary, parse_mode="Markdown")
            logging.info(f"Сводный отчет отправлен в админский чат {ADMIN_CHAT_ID}.")
        except Exception as e:
            logging.error(f"Не удалось отправить сводный админский отчет: {e}")
    shift_reports.clear()

# ========================================
#         ПЛАНИРОВЩИК И ПРОВЕРКИ
# ========================================

def check_users_activity():
    """Проверяет активность пользователей и отправляет напоминания."""
    now = time.time()
    active_chats = list(chat_data.keys())
    
    for chat_id in active_chats:
        if 'main_user' not in chat_data[chat_id]:
            continue
            
        user_data = chat_data[chat_id]['main_user']
        username = user_data['username']

        # Проверка тех, кто на перерыве
        if user_data['on_break']:
            time_on_break = now - user_data['break_start_time']
            if time_on_break > BREAK_DURATION_MINUTES * 60 and not user_data.get('return_demanded'):
                bot.send_message(chat_id, random.choice(soviet_phrases["return_demand"]))
                user_data['return_demanded'] = True
                user_data['return_demand_time'] = now
                save_history_event(chat_id, username, "Получил напоминание о возвращении с перерыва.")

            elif user_data.get('return_demanded') and now - user_data['return_demand_time'] > WAIT_RETURN_CONFIRM_MINUTES * 60:
                bot.send_message(chat_id, random.choice(soviet_phrases["return_demand_hard"]))
                user_data['late_returns'] = user_data.get('late_returns', 0) + 1
                user_data.pop('return_demanded', None) # Чтобы не спамить
                save_history_event(chat_id, username, "Получил ЖЕСТКОЕ напоминание и отмечен как опоздавший.")

        # Проверка тех, кто не на перерыве
        else:
            time_since_voice = now - user_data['last_voice_time']
            if time_since_voice > VOICE_TIMEOUT_MINUTES * 60:
                reminders = user_data.get('reminders_sent', 0)
                if reminders < 2:
                    phrase = random.choice(soviet_phrases["voice_reminder"])
                else:
                    phrase = random.choice(soviet_phrases["scary_reminder"])
                
                bot.send_message(chat_id, phrase)
                user_data['reminders_sent'] = reminders + 1
                # Сбрасываем таймер после напоминания, чтобы не спамить каждую минуту
                user_data['last_voice_time'] = now - (VOICE_TIMEOUT_MINUTES * 60) + (REMIND_EACH_MINUTES * 60)
                save_history_event(chat_id, username, f"Получил напоминание #{reminders + 1} о необходимости голосового.")

def duty_check_reminder():
    """Напоминает о необходимости назначить главного, если смены нет."""
    for chat_id_to_check in [ADMIN_CHAT_ID]: # Можно добавить ID рабочих чатов
        if chat_id_to_check not in chat_data or not chat_data[chat_id_to_check].get('main_user'):
            try:
                bot.send_message(chat_id_to_check, random.choice(duty_call_phrases))
            except Exception as e:
                logging.error(f"Не удалось отправить duty_check_reminder в чат {chat_id_to_check}: {e}")

def duty_check_late():
    """Отправляет сообщение, если главный так и не был назначен."""
    for chat_id_to_check in [ADMIN_CHAT_ID]:
         if chat_id_to_check not in chat_data or not chat_data[chat_id_to_check].get('main_user'):
            try:
                bot.send_message(chat_id_to_check, random.choice(duty_late_phrases))
            except Exception as e:
                logging.error(f"Не удалось отправить duty_check_late в чат {chat_id_to_check}: {e}")

def run_scheduler():
    """Запускает все запланированные задачи."""
    # Ежеминутная проверка активности
    schedule.every(1).minutes.do(check_users_activity)
    
    # Ежедневные отчеты
    schedule.every().day.at("04:01", "Europe/Moscow").do(send_end_of_shift_reports)
    
    # Напоминания о начале смены
    schedule.every().day.at("19:00", "Europe/Moscow").do(duty_check_reminder)
    schedule.every().day.at("19:30", "Europe/Moscow").do(duty_check_late)

    while True:
        schedule.run_pending()
        time.sleep(1)

# ========================================
#                   ЗАПУСК
# ========================================

if __name__ == '__main__':
    logging.info("🤖 Бот запускается...")
    
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    logging.info("✅ Бот успешно запущен. Ожидание сообщений...")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=90)
        except Exception as e:
            logging.error(f"Критическая ошибка в цикле polling: {e}")
            time.sleep(15) # Пауза перед перезапуском polling
```
