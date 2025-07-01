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

# --- Настройки ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")

SHIFT_START_HOUR = 19
SHIFT_END_HOUR = 4
VOICE_TIMEOUT_MINUTES = 40
REMIND_EACH_MINUTES = 5
BREAK_DURATION_MINUTES = 15
EXPECTED_VOICES_PER_SHIFT = 15
MIN_VOICE_SECONDS = 7
BREAK_DELAY_MINUTES = 60  # Перерыв можно не чаще 1 раза в BREAK_DELAY_MINUTES

ADMIN_CHAT_ID = -1002645821302
shift_reports = []

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN)

# --- Фразы ---
welcome_phrases = [
    "🎙️ Добро пожаловать, ведущий! Эфир ждет не болтовни, а работы.",
    "📻 Я тут, чтобы следить за твоей дисциплиной. Готовь голосовые.",
    "🕵️‍♂️ Я контролирую эфир. Не подведи.",
    "🔔 Теперь за тобой наблюдают. Не расслабляйся.",
    "🎤 Твой голос – твой KPI. Хватит халтуры, работаем!",
    "🚀 Не забудь: голосовое не будет – премии не будет.",
    "📝 Всё под контролем, каждое слово на счету.",
    "⏳ Время работает против тебя, если ты молчишь.",
    "😊 Рад тебя видеть. Но руководство ждёт действий.",
    "😎 Здесь не болото – каждый голос важен!",
]

soviet_phrases = {
    "voice_reminder": [
        "😡 Где голосовое? Пинка получишь сейчас!",
        "⛔️ Ты что, бессмертный? Голосовое или по жопе!",
        "🚨 В эфире тишина! Давай голосовое, пока не отвезли в лес!",
        "🕳️ Провалишь смену — объяснять будешь лесорубам.",
        "😤 Эфир не резиновый. Время пошло, текст будет, или тапки?",
        "💀 Молчание — путь к штрафу. Голосовое — быстро!",
        "🥶 Без твоего текста эфир замерзает. Не дразни судьбу.",
        "😠 Или ты работаешь, или тебя давно в лес не вывозили?",
        "👿 Следующее напоминание — с ремнем.",
        "🤬 Руководство на низком старте. Где текст?",
        "📉 Каждый пропуск — минус к премии. Не нарывайся.",
        "⚠️ Ты опять игноришь эфир? Пинка хочешь?",
        "🚩 Срочно текст ведущего! Или выедешь на природу — без возврата.",
        "🔥 Или ты оживляешь эфир, или эфир оживит тебя.",
        "📢 Где твой голос? Не позорься, работай!",
        "😬 Давай, пока не поздно. Голосовое сюда, иначе получишь по пятой точке.",
        "👊 Будет тишина — будет разнос. Не испытывай меня.",
        "🛑 Голосовое! Не хочешь остаться без штанов?",
        "🗣️ Молчишь? Значит, премии не будет и тапки готовь.",
        "☠️ Ну что, бездельник, эфир ждёт! Голосовое! Или бегом в лес.",
        "🤡 Думаешь, забуду? У меня память как у начальства.",
        "😤 Каждый раз, когда ты молчишь, где-то плачет твой кошелёк.",
        "💢 Не доводи до красной строки отчёта, иначе ремень.",
        "🥵 Грею ремень, если не будет голосового.",
        "🦾 Не хочешь работать — выезд за город обеспечен.",
        "🎤 Молчание — это не выход, это билет на дачу.",
        "🤖 Даже роботы говорят больше, чем ты. Учись у техники.",
        "🦷 Ты зубы дома забыл или просто боишься микрофона?",
        "🥊 Хочешь урок дисциплины — продолжай молчать.",
        "🪓 Не тяни — эфир сейчас сам тебя подтянет.",
        "🐒 Даже обезьяна смогла бы отправить голосовое.",
        "🔥 Где твой огонь? Или ты уже тухляк?",
        "🧨 Вот-вот взорвусь, если не будет текста.",
        "🤬 Достал уже молчать! Голосовое, быстро!",
        "😈 Я могу быть очень неприятным. Проверь.",
        "🔥 Не бойся микрофона, бойся меня без отчёта.",
        "👹 Эфир не ждёт — он требует.",
        "🦵 Пора поднять свою задницу и сделать дело!",
        "🪤 Не попадай в ловушку молчания, иначе ловушка найдёт тебя.",
        "🚒 Эфир горит, а ты молчишь — тушить будешь?",
        "👺 Устал ждать твой голос.",
        "🦉 Даже сова ночью активнее.",
        "🤏 Твой вклад пока меньше нуля.",
        "🎲 Хочешь сыграть в увольнение?",
        "🦾 Включи режим работы, а не симуляции.",
        "🕳️ В яму лени быстро попадёшь.",
        "🦦 Выдра бы уже записала голосовое.",
        "🦖 Динозавр вымер, потому что молчал.",
        "🦨 Запах лени доносится до Москвы.",
        "🍑 Не жди, что кто-то другой тебя выручит.",
        "👎 Молчание — худший вклад в эфир.",
        "🙉 Даже обезьяна с микрофоном громче тебя.",
        "🤬 Если не слышу твой голос — считаю тебя бездельником.",
        "💩 Такой работы даже унитаз не видел.",
        "🛑 Последний раз предупреждаю — потом разнос.",
        "🤬 Просто скажи что-нибудь, иначе мне придётся.",
        "🤯 Взрываю свой мозг от твоего молчания.",
        "🐷 Пора перестать хрюкать и начать работать.",
        "🦆 Кря-кря — даже утка в эфире активнее.",
        "🦧 Сколько можно ждать? Голосовое — сейчас!",
        "🦍 Не будь гориллой, говори нормально.",
        "🦜 Я не попугай, но повторю: ГОЛОСОВОЕ!",
        "🐲 Дракон уже подлетает к твоей пятой точке.",
    ],
    "scary_reminder": [
        "👿 Следующее напоминание — с ремнем и выездом в лес.",
        "🪓 Ты доиграешься, если не пришлёшь голосовое.",
        "💀 Тебя давно не вывозили на природу? Продолжай молчать.",
        "😈 Жду текст ведущего. Последний шанс, дальше будет больно.",
        "👻 Эфир пустеет. За тобой уже следят.",
        "⏳ Каждая минута без текста — твоя боль.",
        "🔪 Не доводи до жёстких мер. Я могу быть очень убедительным.",
        "🩸 Текст ведущего или... жёсткий выговор и объяснительная.",
        "😱 Ты на грани провала смены. Очнись!",
        "🛑 Последнее предупреждение. Голосовое — сейчас, иначе по жопе.",
        "⚡️ Руководство уже в курсе твоей бездеятельности.",
        "👻 В темноте за молчуном приходит начальник.",
        "🦷 За каждое молчание я съедаю один твой зуб.",
        "💀 Премии не будет — будет позор.",
        "🦾 Не шевелишься — не живёшь.",
        "👀 Я слежу за каждым твоим молчанием.",
        "🗡️ Молчание — смертный грех для ведущего.",
        "🐍 Змея увольнения уже рядом.",
        "🦆 Крякни хоть что-нибудь, чтобы выжить.",
        "🦖 Вымрешь, как динозавр!",
        "🦇 Я везде — даже в твоих снах.",
        "🦨 Запах лени дошёл до начальства.",
        "😈 Не доводи до греха — говори.",
        "🦴 Если не хочешь проблем — голосовое сейчас.",
        "🦷 Готовься к объяснительной записке.",
        "🦾 Я не устану напоминать, но ты устанешь слушать.",
        "🦎 Лень — твой враг.",
        "🦔 Ёжик уже начал писать на тебя жалобу.",
        "🦡 Барсук не одобрит тишину.",
        "🦩 Фламинго уволили за молчание.",
        "🦃 Индюк был в эфире — теперь его нет.",
        "🦦 Выдра бдит.",
        "🦚 Павлин ждёт твоей активности.",
        "🦢 Белый лебедь не принесёт премию.",
        "🦜 Попугай повторит твой текст — но его нет.",
        "🦖 Не стань вымершим.",
        "🦆 Не хочешь, чтобы тебя съели — работай.",
        "🦨 Не хочешь вонять ленью — говори.",
        "🦔 Ёжик уже близко.",
        "🦡 Барсук недоволен.",
        "🦩 Фламинго грустит по тебе.",
    ],
    "break_acknowledgement": [
        "☕ Перерыв засчитан, {username}. Смотри, чтобы не затянулся.",
        "🍔 Быстро перекуси и назад работать.",
        "🕰️ 15 минут и не секундой больше.",
        "🍵 Перерыв, но не расслабляйся.",
        "🥨 Через 15 минут жду голосовое.",
        "🍫 Не забудь вернуться вовремя.",
        "🧃 Отдыхай, но премию за опоздание не жди.",
        "🥯 Всё под контролем. Перерыв пошёл.",
        "🍋 Не задерживайся в столовой.",
        "🥤 Потом снова за работу.",
    ],
    "break_too_soon": [
        "❌ Не наглей! Перерыв только раз в час. Терпи ещё {minutes} мин. Не раскисай!",
        "🕐 Ты недавно отдыхал. Ещё рано, работай! До следующего перерыва {minutes} мин.",
        "⏳ Перерыв не раньше чем через {minutes} мин. Терпи, эфир не любит слабаков.",
        "💢 Ты только что оторвал пятую точку от стула. Подожди ещё {minutes} мин.",
        "🥊 Перерыв раз в час! Осталось {minutes} мин. Держись, не разваливайся.",
        "🥵 Не получится так часто отдыхать. Жди ещё {minutes} мин.",
        "👊 Терпи, работяга! Следующий перерыв через {minutes} мин.",
        "🔥 Слишком часто отдыхаешь! До следующего перерыва жди ещё {minutes} мин.",
        "😤 Хватит халтурить. До перерыва ещё {minutes} мин.",
        "🛑 Перерыв не положен! До разрешения ещё {minutes} мин.",
    ],
    "too_short": [
        "🗑️ Ты это сейчас всерьёз? Голосовое меньше 7 секунд — даже читать стыдно.",
        "⏳ Такой короткий текст даже ёжик бы не принял.",
        "😤 Меньше 7 секунд — не считается! Не халтурь.",
        "👎 Это не голосовое, а микро-пердеж. Перезапиши!",
        "🙄 Если не можешь наговорить хотя бы 7 секунд — зачем ты здесь?",
    ],
    "accept": [
        "✅ Принято. Следи за сменой, не расслабляйся.",
        "👌 Годится. Но если будешь халтурить — пинка получишь!",
        "👍 Отметил. Ещё пару таких — и, может быть, не уволю.",
        "🚩 Зафиксировал. Но если голосовых мало — выезжаем в лес.",
        "😏 Принято, но расслабляться рано. Я за тобой слежу!",
        "🦾 Так держать. Но отдыхать будешь только после смены.",
        "👀 Принял. За каждым твоим словом — мой зоркий глаз.",
        "😈 Пока хорошо, но попробуй только замолчать.",
        "📝 Записал. Но если план не сделаешь — сам знаешь что будет.",
        "🔥 Пошло дело. Но держи темп, иначе тапки готовь.",
        "👊 Вот это по-нашему! Только не сбавляй обороты.",
        "🦵 Принято. За слабину — по пятой точке.",
        "🥶 Не дай замёрзнуть эфиру. Держи темп!",
        "🤡 Не цирк, а работа. Продолжай!",
        "😬 Принято. Но если будешь тупить — ремень рядом.",
        "🚨 Всё зафиксировал. Не расслабляйся!",
        "🍑 По жопе не хочешь? Тогда продолжай в том же духе.",
        "😜 Молодец. Но только попробуй уйти в тень.",
        "🚀 Поехали дальше! Эфир любит активных.",
        "💪 Вот так бы всегда. Но я всё равно слежу.",
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

def get_chat_title(chat_id):
    try:
        title = bot.get_chat(chat_id).title
        return title if title else str(chat_id)
    except Exception:
        return str(chat_id)

@bot.message_handler(commands=["start"])
def send_welcome(message):
    # Автоматический старт
    if message.chat.id == ADMIN_CHAT_ID:
        return
    if message.text.strip().lower().startswith("/start @"):
        # Ручное назначение главного по тегу - см. /start @username
        match = re.match(r'/start\s+@([a-zA-Z0-9_]+)', message.text.strip())
        if match:
            requested_username = "@" + match.group(1)
            chat_id = message.chat.id
            if chat_id not in chat_data:
                bot.reply_to(message, "🚫 В этом чате ещё никого не было.")
                return
            users = chat_data[chat_id]['users']
            uid, userinfo = get_user_by_username(users, requested_username)
            if uid:
                chat_data[chat_id]['main_id'] = uid
                chat_data[chat_id]['main_username'] = requested_username
                bot.send_message(chat_id, f"⚡️ Ручное назначение: {requested_username} теперь главный на смене! Не забудь, халява не пройдёт — держи эфир!")
            else:
                bot.reply_to(message, f"Не найден пользователь {requested_username} в этом чате.")
        else:
            bot.reply_to(message, "Формат команды: /start @username")
        return
    welcome_message = random.choice(welcome_phrases)
    bot.reply_to(message, welcome_message)

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)
    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'main_username': None, 'users': {}, 'shift_start': now, 'chat_title': get_chat_title(chat_id)}
    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = {'username': username, 'count': 0, 'reminded': False, 'on_break': False, 'breaks_count': 0, 'late_returns': 0, 'last_remind_time': None}
    user = users[user_id]
    # НЕ засчитываем голосовое короче 7 секунд!
    voice_duration = message.voice.duration
    if voice_duration < MIN_VOICE_SECONDS:
        bot.send_message(chat_id, random.choice(soviet_phrases["too_short"]))
        return

    user['count'] += 1
    user['last_voice_time'] = now
    user['reminded'] = False
    user['last_remind_time'] = None
    chat_data[chat_id]['chat_title'] = get_chat_title(chat_id)
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        chat_data[chat_id]['shift_start'] = now
        users[user_id]['last_voice_time'] = now
        text = f"{username}, теперь ты главный. Не забудь: голосовой — твоя обязанность!"
        bot.send_message(chat_id, text)
    elif chat_data[chat_id]['main_id'] == user_id and user['count'] > 1:
        bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['accept'])}")
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
    now = datetime.datetime.now(moscow_tz)
    if chat_id not in chat_data or chat_data[chat_id].get('main_id') != user_id:
        bot.reply_to(message, "⛔ Перерыв только для главного на смене. Не нарушай порядок.")
        return
    user = chat_data[chat_id]['users'][user_id]
    last_break_time = user.get('last_break_time')
    if last_break_time:
        minutes_since_last_break = (now - last_break_time).total_seconds() / 60
        if minutes_since_last_break < BREAK_DELAY_MINUTES:
            remaining = int(BREAK_DELAY_MINUTES - minutes_since_last_break)
            phrase = random.choice(soviet_phrases["break_too_soon"]).format(minutes=remaining)
            bot.reply_to(message, phrase)
            return
    user['breaks_count'] += 1
    user['on_break'] = True
    user['break_start_time'] = now
    user['last_break_time'] = now
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
        bot.send_message(chat_id, "🔄 Смена перезапущена. Жду нового голосового для назначения главного!")

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
                    phrase = random.choice(soviet_phrases["return_success"])
                    bot.send_message(chat_id, f"{user['username']}, {phrase}")
                    user['reminded'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о конце перерыва: {e}")
            continue
        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES:
                if not user.get('last_remind_time') or (now - user['last_remind_time']).total_seconds() / 60 >= REMIND_EACH_MINUTES:
                    if random.random() < 0.5:
                        phrase = random.choice(soviet_phrases["scary_reminder"])
                    else:
                        phrase = get_reminder_phrase()
                    bot.send_message(chat_id, f"{user['username']}, {phrase}")
                    user['last_remind_time'] = now
            else:
                user['last_remind_time'] = None

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
    chat_title = data.get('chat_title') or get_chat_title(chat_id)
    report_lines = [
        f"📋 #Промежуточный_отчет ({data['shift_start'].strftime('%d.%m.%Y')})",
        f"🏢 Чат: {chat_title}",
        f"🎤 Ведущий: {username}",
        f"🗣️ Голосовых: {said_count} из {EXPECTED_VOICES_PER_SHIFT} ({perc}%)",
        f"☕ Перерывов: {breaks_count}",
        f"⏳ Задержек после перерыва: {late_returns}",
    ]
    return report_lines

@bot.message_handler(commands=["промежуточный", "promezhut"])
def send_interim_report(message):
    chat_id = message.chat.id
    if chat_id not in chat_data:
        bot.send_message(chat_id, "Нет данных по смене в этом чате.")
        return
    report_lines = get_report_lines(chat_id, chat_data[chat_id])
    bot.send_message(chat_id, "\n".join(report_lines))

def send_end_of_shift_reports():
    now = datetime.datetime.now(moscow_tz)
    for chat_id, data in chat_data.items():
        main_id = data.get('main_id')
        users = data.get('users', {})
        main_user = users.get(main_id)
        if not main_user:
            continue
        breaks_count = main_user.get('breaks_count', 0)
        late_returns = main_user.get('late_returns', 0)
        said_count = main_user.get('count', 0)
        perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100)
        username = main_user.get('username', 'Неизвестно')
        chat_title = data.get('chat_title') or get_chat_title(chat_id)
        praise = ""
        if perc >= 80:
            praise = "\n\n" + random.choice(soviet_phrases["praise"])
        elif perc >= 50:
            praise = "\n\n" + random.choice(soviet_phrases["voice_reminder"])
        elif perc < 50:
            praise = "\n\n⚠️ Смена провалена, эфир был слишком тихим!"
        report_lines = [
            f"📋 #Отчет_Текст_Ведущего ({data['shift_start'].strftime('%d.%m.%Y')})",
            f"🏢 Чат: {chat_title}",
            f"🎤 Ведущий: {username}",
            f"🗣️ Всего голосовых: {said_count} из {EXPECTED_VOICES_PER_SHIFT} ({perc}%)",
            f"☕ Перерывов: {breaks_count}",
            f"⏳ Задержек после перерыва: {late_returns}",
            praise
        ]
        final_report = "\n".join([line for line in report_lines if line.strip()])
        try:
            bot.send_message(chat_id, final_report)
        except Exception as e:
            logging.error(str(e))
        shift_reports.append({
            "chat_id": chat_id,
            "chat_title": chat_title,
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
        chat_title = item.get("chat_title", "")
        for line in lines:
            if "Всего голосовых" in line:
                try:
                    said_count = int(line.split(":")[1].split("из")[0].strip())
                    expected = int(line.split("из")[1].split("(")[0].strip())
                except Exception:
                    pass
            if "Задержек после перерыва" in line:
                try:
                    late_returns = int(line.split(":")[1].strip())
                except Exception:
                    pass
        perc = round(said_count / expected * 100) if expected else 0
        conclusion = get_official_conclusion(perc, late_returns)
        report_lines.append(f"🏢 Чат: {chat_title}")
        report_lines.append(item["report"])
        report_lines.append(conclusion)
        report_lines.append("")
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
