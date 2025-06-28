import logging
import os
import telebot
import datetime
import pytz
import time
import schedule
import threading
import random

# --- Настройки ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")

SHIFT_START_HOUR = 19
SHIFT_END_HOUR = 4
VOICE_TIMEOUT_MINUTES = 40  # через сколько напоминать впервые
REMIND_EACH_MINUTES = 5     # далее каждые сколько минут напоминать
BREAK_DURATION_MINUTES = 15
EXPECTED_VOICES_PER_SHIFT = 15

ADMIN_CHAT_ID = -1002645821302  # <-- id чата руководства!
shift_reports = []

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN)

# --- Фразы ---
welcome_phrases = [
    "🎙️ Добро пожаловать, ведущий! Эфир ждет твоих слов.",
    "📻 Привет! Я уже на связи — буду считать твои голосовые.",
    "🕵️‍♂️ На страже эфира! Всё под контролем.",
    "🔔 Ты в эфире — теперь за тобой слежу я!",
    "🎤 Ожидаю твоих текстов. Давай сделаем этот эфир лучшим!",
    "🚀 Вперёд, ведущий! Голосовые — твой путь к успеху.",
    "📝 Всё, что скажешь — будет учтено. Я внимателен.",
    "⏳ Не забывай про отчёт — я не дремлю.",
    "😊 Рад видеть тебя на смене! Пусть будет весело.",
    "😎 Ты готов? Тогда поехали!",
    "🤝 Дружище, я тут, чтобы помочь с подсчётом.",
    "🔊 Любое твое слово — уже вклад в эфир.",
    "📅 Рабочий день начинается! Не забудь голосовое.",
    "🥳 Пусть эта смена будет продуктивной!",
    "🎲 Давай добавим немного креатива в эфир.",
    "🌈 Сделай эфир ярче своим голосом.",
    "💡 Я отмечаю все твои идеи.",
    "🦾 Автоматизация включена. Ведущий, давай работать!",
    "🌟 Каждый твой голос — это звезда в эфире.",
    "✨ Вдохновляй слушателей!",
    "🎧 Я всё считаю. Не переживай, ничего не забуду.",
    "🛠️ Если что — всегда помогу советом.",
    "📢 Готовь тексты, я готов их слушать.",
    "🧐 За дисциплиной слежу я — не подведи!",
    "🚦 Поехали — эфир ждёт!",
    "🖇️ Счётчик голосов запущен.",
    "💬 Не молчи — эфир любит болтать.",
    "👨‍💼 Давай покажем руководству, как надо работать!",
    "🎶 Пусть твой голос звучит как музыка.",
    "👋 Привет, герой эфира!",
    "🚨 Внимание! Смена началась.",
    "📈 Пусть график твоих голосовых будет круче всех.",
    "🧭 Держу путь по голосовым сообщениям.",
    "📊 Каждое сообщение приближает нас к успеху.",
    "🕰️ Таймер пошёл — не пропусти первое голосовое.",
    "⚡ Заряжай эфир энергией!",
    "🏆 Будь чемпионом по голосовым.",
    "🎺 Труби в эфир — я всё услышу.",
    "🖖 Удачи сегодня на смене!",
    "🥇 Пусть эта смена станет рекордной!"
]

soviet_phrases = {
    "voice_reminder": [
        "🔔 Напоминаю про текст ведущего.",
        "📢 Жду текст ведущего.",
        "🎙️ Не забывай про голосовое.",
        "⏰ Время прислать текст ведущего.",
        "📻 Эфир ждёт твоего голосового.",
        "🔊 Пора записать голосовое.",
        "💬 Не оттягивай, присылай текст.",
        "📡 Эфиру нужна активность.",
        "🎤 Дай знать, что ты здесь.",
        "🛎️ Не молчи — эфир ждёт.",
        "🎵 Текст ведущего — музыка для эфира.",
        "📞 Ждём твоего сообщения.",
        "🗣️ Эфир любит голосовые.",
        "🎧 Не забывай про эфир.",
        "📝 Отметься голосовым.",
        "📊 Для отчёта нужен текст.",
        "🖇️ Не забудь про свой долг.",
        "🎬 Пора действовать.",
        "🔄 Напомню ещё раз, если что.",
        "🕰️ Не тяни — время идёт.",
        "📲 Эфир всегда рад.",
        "💡 Поделись мыслями вслух.",
        "🦾 Покажи пример для остальных.",
        "🎯 Достигни плана по голосовым.",
        "📆 Не забывай про смену.",
        "🦉 Ждём твоего сообщения.",
        "📚 Держу статистику — не забывай.",
        "📑 Для отчёта нужен твой голос.",
        "🎶 Давай оживим эфир.",
        "🎸 Пусть твой голос прозвучит.",
        "🥁 Дай ритм смене.",
        "🎺 Засветись в эфире.",
        "🥳 Сделай эфир весёлым.",
        "😎 Будь активнее.",
        "🤩 Жду твоего креатива.",
        "🤓 Не забывай про план.",
        "🤖 Бот всегда на связи.",
        "🥇 Будь первым в голосовых.",
        "🏁 Не отставай от плана.",
        "🚦 Давай, ведущий, эфир ждёт."
    ],
    "scary_reminder": [
        "😈 Если не будет текста ведущего — придёт инспектор эфира.",
        "👹 Ты же не хочешь гнев руководства?",
        "🕷️ Без текста ведущего эфир погибает.",
        "🧟‍♂️ Не дразни эфир молчанием!",
        "👾 Риск потерять премию растёт.",
        "💀 Не доводи до чёрного списка.",
        "👻 Если не будет текста — придёт приведение бота.",
        "🔪 Руководство уже рядом.",
        "🧙‍♂️ Я наложу заклинание, если не будет текста.",
        "🦹‍♂️ Не вызывай тёмную сторону эфира.",
        "🦇 В эфире становится темно.",
        "👺 Прячешься? Эфир всё равно найдёт тебя.",
        "🐉 Дракон не любит тишину.",
        "🦠 Вирус молчания опасен.",
        "👽 Инопланетяне ждут текст ведущего.",
        "🦈 Акула эфира кружит рядом.",
        "🦝 Енот-босс проверяет голосовые.",
        "🦑 Не забудь, иначе будет кара.",
        "🐍 Змей молчания приближается.",
        "🦅 Орёл эфира следит.",
        "🦖 Динозавр-начальник гневается.",
        "🦆 Утка ждет текст ведущего.",
        "🦢 Белый лебедь не принесёт премию.",
        "🦜 Попугай повторит твой текст — но его нет.",
        "🦚 Павлин ждёт похвалы, но кто-то молчит.",
        "🦩 Фламинго расстроен.",
        "🦃 Индюк эфира недоволен.",
        "🦦 Выдра бдит.",
        "🦨 Скунс скоро появится.",
        "🦥 Ленивец не так уж и медлителен.",
        "🦦 Не ленись, эфир ждёт.",
        "🦔 Ёжик ждёт текст ведущего.",
        "🦡 Барсук не одобрит тишину.",
        "🦃 Турция премий не будет.",
        "🦚 Не доводи до крайних мер.",
        "🦩 Скоро будет совещание.",
        "🦜 Где ты, ведущий?",
        "🦢 Молчание — не золото.",
        "🦚 Последний шанс!"
    ],
    "break_acknowledgement": [
        "☕ Перерыв принят, {username}. Не забудь вовремя вернуться!",
        "🍰 Приятного аппетита, {username}!",
        "🥤 Отдохни, {username}, но не очень долго.",
        "🧁 Перерыв засчитан, {username}!",
        "🕰️ Таймер на 15 минут пошёл.",
        "🍫 Подкрепись, потом к голосовым.",
        "🍵 Чай-кофе — святое!",
        "🥪 Перекусить — тоже работа.",
        "🍲 Приятного отдыха.",
        "🍹 Главное — вернуться вовремя.",
        "🍔 Не забудь про эфир.",
        "🥗 Жду тебя после перерыва.",
        "🍦 Сладкий отдых, {username}!",
        "⏳ Время пошло.",
        "🛋️ Расслабься, ты заслужил.",
        "🥒 Не задерживайся.",
        "🥤 Возвращайся бодрым.",
        "🍉 Эфир пока подождёт.",
        "🥨 Приятного чаепития.",
        "🍛 Кушай вкусно.",
        "🍟 Перерыв приятен, эфир важнее.",
        "🍳 До встречи после отдыха.",
        "🥧 Работа подождёт.",
        "🍪 После перерыва — к голосовым.",
        "🧃 Зарядись энергией.",
        "🍍 Ведущий должен быть сыт.",
        "🥭 Силы пополнены? Возвращайся.",
        "🍇 Поработал — теперь отдохни.",
        "🍄 Перерыв — это не отпуск.",
        "🍩 Не задерживайся на кухне.",
        "🥤 Пей, ешь, отдыхай.",
        "🥝 Потом поболтаем, а пока отдых.",
        "🍋 После перерыва — в бой.",
        "🍊 Ждём твоего возвращения.",
        "🍏 Не забывай про эфир.",
        "🍐 Вернёшься — продолжим.",
        "🍎 Перерыв — это святое.",
        "🍅 Не затягивай.",
        "🍒 До скорого, ведущий.",
        "🍓 15 минут и снова эфир."
    ],
    "praise": [
        "🥳 Молодец! Ты справился на отлично! 👏",
        "🚀 Отличная работа! План выполнен! 🏅",
        "🔥 Так держать! Ты на высоте! 🏆",
        "🌟 Пример для остальных! Продолжай в том же духе! 💡",
        "🎉 Ты герой эфира! Браво! 🎺",
        "💪 Легенда смены! Так держать! 🏆",
        "🍀 Удача всегда с тобой! 👍",
        "😉 Руководство довольно! 🥂",
        "🦸‍♂️ Ты суперведущий! Продолжай! 💪",
        "🕺 Твои голосовые — праздник для эфира! 🎈",
        "🏅 Отличный результат!",
        "⚡ Энергия зашкаливает.",
        "📈 График голосовых выше всех.",
        "🎶 Твой голос — украшение эфира.",
        "🎯 Попадание в цель!",
        "🧲 Притягиваешь успех.",
        "🖖 Так держать!",
        "🧩 Все части эфира на месте.",
        "🎬 Лучшая смена!",
        "🌞 Твой голос — луч солнца.",
        "🍉 Сочная работа!",
        "🎤 Голос ведущего — главный инструмент.",
        "📻 Руководство в восторге.",
        "🎺 Труби так же дальше!",
        "👨‍🎤 Настоящий артист эфира.",
        "🥰 Эфир любит твои сообщения.",
        "🎊 Праздник на эфире.",
        "🍫 Вкусная работа.",
        "🧠 Мозг эфира.",
        "💡 Светлая голова!",
        "🎓 Эталон для других.",
        "📚 Учебник по дисциплине.",
        "🔔 Всегда вовремя.",
        "⏰ Ни одной задержки.",
        "🦾 Железная дисциплина.",
        "🏁 Финишировал первым.",
        "🏆 Чемпион эфира.",
        "🥇 Золотой ведущий.",
        "👏 Аплодисменты!",
        "🚀 Ракетный прогресс."
    ],
    "return_success": [
        "✅ С возвращением, {username}! Всё под контролем.",
        "👍 Отлично, {username}. Перерыв окончен — эфир ждёт.",
        "👏 Молодец, {username}! Снова на связи.",
        "🎩 Ну что, {username}, продолжаем работать?",
        "🕺 {username}, ты в строю — эфир доволен!",
        "🏅 Вот это дисциплина, {username}!",
        "🎯 Приятно видеть тебя снова, {username}!",
        "🌞 Добро пожаловать обратно, {username}.",
        "🛠️ Перерыв завершён, к работе {username}!",
        "🚦 Двигайся вперёд, {username}, эфир твой.",
        "🌈 С возвращением, настроение отличное!",
        "🎬 Продолжаем эфир, {username} на месте.",
        "🦾 {username}, ты — пример для других!",
        "🌟 Вернулся вовремя — так держать.",
        "🎤 Голос ведущего вновь в эфире!",
        "📻 Без тебя было скучно, {username}.",
        "🕶️ Как всегда пунктуален, {username}.",
        "🧭 Вперёд к новым голосовым!",
        "📈 Ведущий на месте — эфир в безопасности.",
        "💪 {username}, продолжаем работать.",
        "🍀 Пусть остаток смены будет лёгким!",
        "🥳 Рады видеть тебя снова.",
        "🥂 За твоё возвращение, {username}!",
        "🚀 Вперёд, к новым свершениям.",
        "🧩 Без тебя эфир был не полный.",
        "🎶 Эфир снова зазвучал.",
        "🏁 Ведущий вернулся, эфир стартует.",
        "🎲 Не будем больше рисковать перерывами.",
        "👨‍💼 Руководство довольно!",
        "🧠 Не забывай про голосовые, {username}.",
        "👋 Приветствую обратно!",
        "🔔 Всё, перерыв закончен.",
        "⏰ Время работать!",
        "🎉 Отличная дисциплина, {username}!",
        "🦸 Ты — герой эфира.",
        "🏆 С возвращением к победе.",
        "🍫 Перерыв завершён, а теперь к голосовым.",
        "📢 Ведущий снова на связи.",
        "🕵️ Я всё вижу — ты молодец!",
        "🧑‍🚀 Курс на хороший эфир!"
    ]
}

BREAK_KEYWORDS = [
    "перерыв", "перекур", "покурить", "я на перерыв", "я на обед", "обед", "я кушать",
    "кушать", "ем", "есть", "отдохнуть", "пить", "кофе", "чай", "отойти", "отойду"
]

chat_data = {}

def get_username(message):
    if message.from_user.username:
        return f"@{message.from_user.username}"
    return message.from_user.first_name

def get_user_by_username(users_dict, username):
    for uid, info in users_dict.items():
        if info['username'].lower() == username.lower():
            return uid, info
    return None, None

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)
    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'main_username': None, 'users': {}, 'shift_start': now}
    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = {'username': username, 'count': 0, 'reminded': False, 'on_break': False, 'breaks_count': 0, 'late_returns': 0, 'last_remind_time': None}
    user = users[user_id]
    user['count'] += 1
    user['last_voice_time'] = now
    user['reminded'] = False
    user['last_remind_time'] = None  # сбросить таймер напоминания после нового голосового
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        chat_data[chat_id]['shift_start'] = now
        users[user_id]['last_voice_time'] = now
        text = f"{username}, теперь ты главный! Не забывай присылать текст ведущего!"
        bot.send_message(chat_id, text)
    elif chat_data[chat_id]['main_id'] == user_id and user['count'] > 1:
        bot.send_message(chat_id, f"{username}, принято! Текст ведущего получен.")
    if user.get('on_break'):
        break_start = user.get('break_start_time')
        if break_start:
            minutes_on_break = (user['last_voice_time'] - break_start).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES:
                user['late_returns'] += 1
        user['on_break'] = False
        bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
    logging.info(f"🎧 Голосовое от {username} в чате {chat_id}. Всего: {users[user_id]['count']}")

def break_requested(text):
    lowered = text.lower()
    return any(word in lowered for word in BREAK_KEYWORDS)

@bot.message_handler(func=lambda m: m.text and break_requested(m.text))
def handle_break_request(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    if getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    if chat_id not in chat_data or chat_data[chat_id].get('main_id') != user_id:
        bot.reply_to(message, "⛔ Перерыв можно брать только главному на смене! 🦻")
        return
    user = chat_data[chat_id]['users'][user_id]
    user['breaks_count'] += 1
    user['on_break'] = True
    user['break_start_time'] = datetime.datetime.now(moscow_tz)
    ack = random.choice(soviet_phrases["break_acknowledgement"]).format(username=username)
    bot.reply_to(message, ack)

@bot.message_handler(commands=["obed"])
def obed_command(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    handle_break_request(message)

@bot.message_handler(commands=["restart"])
def restart_main(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    chat_id = message.chat.id
    if chat_id in chat_data:
        chat_data[chat_id]['main_id'] = None
        chat_data[chat_id]['main_username'] = None
        chat_data[chat_id]['shift_start'] = datetime.datetime.now(moscow_tz)
        bot.send_message(chat_id, "🔄 Смена перезапущена. Жду нового голосового для назначения главного! 🕰️")

def get_reminder_phrase():
    return random.choice(soviet_phrases["voice_reminder"])

def check_users_activity():
    for chat_id, data in chat_data.items():
        main_id = data.get('main_id')
        if not main_id:
            continue
        user = data['users'].get(main_id)
        if not user:
            continue
        now = datetime.datetime.now(moscow_tz)
        if user.get('on_break'):
            minutes_on_break = (now - user['break_start_time']).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES and not user.get('reminded'):
                try:
                    phrase = random.choice(soviet_phrases["praise"])
                    bot.send_message(chat_id, f"{user['username']}, {phrase}")
                    user['reminded'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о конце перерыва: {e}")
            continue
        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES:
                if not user.get('last_remind_time') or (now - user['last_remind_time']).total_seconds() / 60 >= REMIND_EACH_MINUTES:
                    if random.random() < 0.2:
                        phrase = random.choice(soviet_phrases["scary_reminder"])
                    else:
                        phrase = get_reminder_phrase()
                    bot.send_message(chat_id, f"{user['username']}, {phrase}")
                    user['last_remind_time'] = now
            else:
                user['last_remind_time'] = None

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    welcome_message = random.choice(welcome_phrases)
    bot.reply_to(message, welcome_message)

def get_report_lines(chat_id, data):
    main_id = data.get('main_id')
    users = data.get('users', {})
    main_user = users.get(main_id)
    if not main_user:
        return ["Главный ведущий ещё не назначен."]
    breaks_count = main_user.get('breaks_count', 0)
    late_returns = main_user.get('late_returns', 0)
    said_count = main_user.get('count', 0)
    perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100)
    username = main_user.get('username', 'Неизвестно')
    report_lines = [
        f"📋 #Отчет_Текст_Ведущего ({data['shift_start'].strftime('%d.%m.%Y')})",
        f"🏢 Чат: {chat_id}",
        f"🎤 Ведущий: {username}",
        f"🗣️ Всего текстов ведущего: {said_count} из {EXPECTED_VOICES_PER_SHIFT}",
        f"☕ Перерывов: {breaks_count}",
        f"⏳ Задержек после перерыва: {late_returns}",
    ]
    return report_lines

def send_end_of_shift_reports():
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in chat_data.items():
        report_lines = get_report_lines(chat_id, data)
        main_id = data.get('main_id')
        users = data.get('users', {})
        main_user = users.get(main_id)
        if main_user:
            said_count = main_user.get('count', 0)
            perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100)
            if perc >= 80:
                report_lines.append("\n" + random.choice(soviet_phrases["praise"]))
            elif perc >= 50:
                report_lines.append("\n" + random.choice(soviet_phrases["scary_reminder"]))
            else:
                report_lines.append("\n⚠️ Смена провалена, эфир был слишком тихим!")
        final_report = "\n".join([line for line in report_lines if line.strip()])
        try:
            bot.send_message(chat_id, final_report)
        except Exception as e:
            logging.error(str(e))
        shift_reports.append({
            "chat_id": chat_id,
            "date": data['shift_start'].strftime("%d.%m.%Y"),
            "report": final_report
        })
    chat_data.clear()

def get_official_conclusion(perc, late_returns):
    if perc >= 100:
        return "План выполнен полностью."
    elif perc >= 80:
        return "План выполнен частично, сотрудник проявил инициативу."
    elif perc >= 50:
        return "План не выполнен, требуется улучшение дисциплины и активности."
    else:
        return "План провален, требуется разъяснительная работа и строгий контроль."

def send_admin_summary():
    if not shift_reports:
        return
    admin_report_phrases = [
        "@nilfts Я все про них знаю! 🕵️‍♂️ Вот как они отработали:",
        "@nilfts Всё под контролем! Вот свежий отчёт по смене:",
        "@nilfts Докладываю о работе команды! Смотрим результаты:",
        "@nilfts Проверил всех как надо — держу отчёт:",
        "@nilfts Внимание! Сводка по смене готова:",
        "@nilfts Отчёт по смене как на ладони! Вот детали:",
        "@nilfts Всё записал — вот как трудились:",
        "@nilfts Вот их подвиги за смену! Смотрим:",
        "@nilfts Отчёт подготовлен, все данные на месте:",
        "@nilfts Всё под контролем, вот как они работали:",
    ]
    intro = random.choice(admin_report_phrases)
    report_lines = [intro, ""]
    for item in shift_reports:
        lines = item["report"].splitlines()
        said_count = 0
        expected = EXPECTED_VOICES_PER_SHIFT
        late_returns = 0
        for line in lines:
            if "Всего текстов ведущего" in line:
                try:
                    said_count = int(line.split(":")[1].split("из")[0].strip())
                    expected = int(line.split("из")[1].strip())
                except Exception:
                    pass
            if "Задержек после перерыва" in line:
                try:
                    late_returns = int(line.split(":")[1].strip())
                except Exception:
                    pass
        perc = round(said_count / expected * 100) if expected else 0
        conclusion = get_official_conclusion(perc, late_returns)
        report_lines.append(item["report"])
        report_lines.append(conclusion)
        report_lines.append("")  # пустая строка между чатами
    summary = "\n".join(report_lines)
    try:
        bot.send_message(ADMIN_CHAT_ID, summary, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Admin summary error: {e}")
    shift_reports.clear()

@bot.message_handler(commands=["отчет", "otchet"])
def send_manual_admin_report(message):
    if message.chat.id == ADMIN_CHAT_ID:
        send_admin_summary()
        bot.reply_to(message, "Отчёт по смене отправлен руководству.")
    else:
        send_end_of_shift_reports()
        send_admin_summary()
        bot.reply_to(message, "Отчёт по смене отправлен в этот чат и руководству.")

def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("01:01").do(send_end_of_shift_reports)
    schedule.every().day.at("09:00").do(send_admin_summary)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.info("🤖 Бот запущен. Ожидание голосовых для назначения главного на смене... 🎙️")
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling exception: {e}")
            time.sleep(10)
