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
WAIT_RETURN_CONFIRM_MINUTES = 3  # Через сколько минут повторно требовать подтверждение возврата

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
        "☕ Перерыв засчитан, {username}
duty_call_phrases = [
    "👀 Кто сегодня за текст ведущего отвечает? Срочно отметься!",
    "🎤 Кто тут главный? Жду твоего голосового или сообщения!",
    "📣 Эй! Кто сегодня командует эфиром? Не молчать!",
    "⏰ 20:00! Кто отвечает за текст ведущего? Быстро в чат!",
    "🕵️‍♂️ Где главный смены? Не прячься, покажи себя!",
    "🚨 Кто несёт ответственность за эфир? Голосовое — сюда!",
    "🦾 Кто сегодня держит эфир в тонусе? Жду отклика!",
    "👋 Кто главный? Молчание — не вариант!",
    "😈 Не вижу ответственных! Кто сегодня рулит?",
    "📝 Кто за текст ведущего? Без ответственного смена не начнётся!",
    "📢 Жду отметки — кто сегодня отвечает за эфир?",
    "🤷‍♂️ Кто-то должен взять ответственность! Кто?",
]

duty_late_phrases = [
    "😡 Почему не отметился вовремя? Будешь объясняться!",
    "⏰ 20:30 прошло, а главного не видно! Опоздание — минус к репутации!",
    "🛑 Опять проспал? В следующий раз будь оперативней!",
    "😤 Не успел вовремя? За это можно и по жопе получить.",
    "🚨 Смена без ответственного — сразу провал! Где ты был?",
    "😱 До последнего тянул? Так дело не пойдёт!",
    "🤬 Ты что, забыл про смену? Неуважение к эфиру!",
    "👎 Следующий раз опоздаешь — расскажешь начальству.",
    "🔥 Не повторяй это — в следующий раз будет жёстче.",
    "🥵 Не успел отметиться — не жди пощады.",
    "📉 За такие опоздания премии не бывает.",
]

soviet_phrases = {
    # ... СКОПИРУЙТЕ сюда полностью блок soviet_phrases из вашего кода ...
}

duty_call_phrases = [
    # ... СКОПИРУЙТЕ сюда полностью duty_call_phrases ...
]

duty_late_phrases = [
    # ... СКОПИРУЙТЕ сюда полностью duty_late_phrases ...
]

# --- Транслит-функции ---
RU_TO_LAT_LAYOUT = {
    'й':'q', 'ц':'w', 'у':'e', 'к':'r', 'е':'t', 'н':'y', 'г':'u', 'ш':'i', 'щ':'o', 'з':'p', 'х':'[', 'ъ':']',
    'ф':'a', 'ы':'s', 'в':'d', 'а':'f', 'п':'g', 'р':'h', 'о':'j', 'л':'k', 'д':'l', 'ж':';', 'э':'\'',
    'я':'z', 'ч':'x', 'с':'c', 'м':'v', 'и':'b', 'т':'n', 'ь':'m', 'б':',', 'ю':'.',
    'ё':'`',
    'Й':'Q', 'Ц':'W', 'У':'E', 'К':'R', 'Е':'T', 'Н':'Y', 'Г':'U', 'Ш':'I', 'Щ':'O', 'З':'P', 'Х':'{', 'Ъ':'}',
    'Ф':'A', 'Ы':'S', 'В':'D', 'А':'F', 'П':'G', 'Р':'H', 'О':'J', 'Л':'K', 'Д':'L', 'Ж':':', 'Э':'"',
    'Я':'Z', 'Ч':'X', 'С':'C', 'М':'V', 'И':'B', 'Т':'N', 'Ь':'M', 'Б':'<', 'Ю':'>', 'Ё':'~'
}
LAT_TO_RU_LAYOUT = {v: k for k, v in RU_TO_LAT_LAYOUT.items()}

def translit_rus_to_lat(text):
    return ''.join(RU_TO_LAT_LAYOUT.get(ch, ch) for ch in text)

def translit_lat_to_rus(text):
    return ''.join(LAT_TO_RU_LAYOUT.get(ch, ch) for ch in text)

TRANSLIT_COMMANDS = {
    translit_rus_to_lat('промежуточный'): 'promezhut',
    translit_rus_to_lat('отчет'): 'otchet',
    translit_rus_to_lat('обед'): 'obed',
    translit_rus_to_lat('старт'): 'start',
    translit_rus_to_lat('рестарт'): 'restart',
}

BREAK_KEYWORDS = [
    "перерыв", "перекур", "покурить", "я на перерыв", "я на обед", "обед", "я кушать",
    "кушать", "ем", "есть", "отдохнуть", "пить", "кофе", "чай", "отойти", "отойду"
]
BREAK_KEYWORDS += [translit_rus_to_lat(w) for w in BREAK_KEYWORDS]

RETURN_CONFIRM_WORDS = [
    "на месте", "пришел", "пришёл", "покурил", "вернулся", "тут", "готов", "я тут"
]
RETURN_CONFIRM_WORDS += [translit_rus_to_lat(w) for w in RETURN_CONFIRM_WORDS]

chat_data = {}

# --- Handler для транслит-команд ---
@bot.message_handler(func=lambda m: m.text and m.text.startswith('/'))
def translit_command_handler(message):
    cmd = message.text.split()[0][1:].split('@')[0].lower()
    if cmd in TRANSLIT_COMMANDS:
        real_cmd = TRANSLIT_COMMANDS[cmd]
        fake_message = message
        fake_message.text = '/' + real_cmd
        if real_cmd == 'promezhut':
            send_interim_report(fake_message)
        elif real_cmd == 'otchet':
            send_manual_admin_report(fake_message)
        elif real_cmd == 'obed':
            obed_command(fake_message)
        elif real_cmd == 'start':
            send_welcome(fake_message)
        elif real_cmd == 'restart':
            restart_main(fake_message)
        return

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
    if message.chat.id == ADMIN_CHAT_ID:
        return
    if message.text.strip().lower().startswith("/start @"):
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
                bot.send_message(chat_id, f"⚡️ Ручное назначение: {requested_username} теперь главный на смене! Не забудь, халява не пройдет!")
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
        chat_data[chat_id] = {
            'main_id': None,
            'main_username': None,
            'users': {},
            'shift_start': now,
            'chat_title': get_chat_title(chat_id)
        }
    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = {
            'username': username,
            'count': 0,
            'reminded': False,
            'on_break': False,
            'breaks_count': 0,
            'late_returns': 0,
            'last_remind_time': None,
            'waiting_return_confirm': False,
            'remind_return_time': None,
        }
    user = users[user_id]
    voice_duration = message.voice.duration
    if voice_duration < MIN_VOICE_SECONDS:
        bot.send_message(chat_id, random.choice(soviet_phrases["too_short"]))
        return
    user['count'] += 1
    user['last_voice_time'] = now
    user['reminded'] = False
    user['last_remind_time'] = None
    chat_data[chat_id]['chat_title'] = get_chat_title(chat_id)
    if chat_data[chat_id].get('duty_check_time'):
        if now - chat_data[chat_id]['duty_check_time'] < datetime.timedelta(minutes=31):
            chat_data[chat_id]['duty_confirmed'] = True

    if user.get('waiting_return_confirm'):
        user['on_break'] = False
        user['waiting_return_confirm'] = False
        user['reminded'] = False
        user['remind_return_time'] = None
        bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
        if (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
            user['late_returns'] += 1

    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        chat_data[chat_id]['shift_start'] = now
        users[user_id]['last_voice_time'] = now
        text = f"{username}, теперь ты главный. Не забудь: голосовой — твоя обязанность!"
        bot.send_message(chat_id, text)
    elif chat_data[chat_id]['main_id'] == user_id and user['count'] > 1:
        bot.send_message(chat_id, f"{username}, {random.choice(soviet_phrases['accept'])}")

    if user.get('on_break') and not user.get('waiting_return_confirm'):
        break_start = user.get('break_start_time')
        if break_start:
            minutes_on_break = (user['last_voice_time'] - break_start).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES:
                user['late_returns'] += 1
        user['on_break'] = False
        bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
    logging.info(f"🎧 Голосовое от {username} в чате {chat_id}. Всего: {users[user_id]['count']}")

@bot.message_handler(func=lambda m: m.text and m.chat.id != ADMIN_CHAT_ID)
def mark_duty_and_return_if_needed(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)
    now = datetime.datetime.now(moscow_tz)
    if chat_id in chat_data and chat_data[chat_id].get('duty_check_time'):
        if now - chat_data[chat_id]['duty_check_time'] < datetime.timedelta(minutes=31):
            chat_data[chat_id]['duty_confirmed'] = True
    user = chat_data.get(chat_id, {}).get('users', {}).get(user_id)
    if user and user.get('waiting_return_confirm'):
        lowered = message.text.lower()
        lowered_rus = translit_lat_to_rus(lowered)
        if any(word in lowered or word in lowered_rus for word in RETURN_CONFIRM_WORDS):
            user['on_break'] = False
            user['waiting_return_confirm'] = False
            user['reminded'] = False
            user['remind_return_time'] = None
            bot.send_message(chat_id, random.choice(soviet_phrases["return_success"]).format(username=username))
            if (now - user['break_start_time']).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                user['late_returns'] += 1

def break_requested(text):
    lowered = text.lower()
    lowered_rus = translit_lat_to_rus(lowered)
    return any(word in lowered or word in lowered_rus for word in BREAK_KEYWORDS)

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
    user['waiting_return_confirm'] = False
    user['reminded'] = False
    user['remind_return_time'] = None
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
            if minutes_on_break > BREAK_DURATION_MINUTES and not user.get('waiting_return_confirm'):
                phrase = random.choice(soviet_phrases["return_demand"])
                bot.send_message(chat_id, f"{user['username']}, {phrase}")
                user['reminded'] = True
                user['waiting_return_confirm'] = True
                user['remind_return_time'] = now
                continue
        if user.get('waiting_return_confirm'):
            remind_time = user.get('remind_return_time')
            if remind_time and (now - remind_time).total_seconds() / 60 > WAIT_RETURN_CONFIRM_MINUTES:
                phrase = random.choice(soviet_phrases["return_demand_hard"])
                bot.send_message(chat_id, f"{user['username']}, {phrase}")
                user['remind_return_time'] = now
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

def duty_check_reminder():
    now = datetime.datetime.now(moscow_tz)
    for chat_id in chat_data:
        bot.send_message(chat_id, random.choice(duty_call_phrases))
        chat_data[chat_id]['duty_check_time'] = now
        chat_data[chat_id]['duty_confirmed'] = False

def duty_check_late():
    for chat_id, data in chat_data.items():
        if data.get('duty_check_time') and not data.get('duty_confirmed'):
            if data.get('main_id'):
                username = data['users'][data['main_id']]['username']
                bot.send_message(chat_id, f"{username}, {random.choice(duty_late_phrases)}")
            else:
                bot.send_message(chat_id, random.choice(duty_late_phrases))
            data['duty_check_time'] = None
            data['duty_confirmed'] = False

def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    schedule.every().day.at("01:01").do(send_end_of_shift_reports)
    schedule.every().day.at("09:00").do(send_admin_summary)
    schedule.every().day.at("20:00").do(duty_check_reminder)
    schedule.every().day.at("20:31").do(duty_check_late)
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
