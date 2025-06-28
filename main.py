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
VOICE_TIMEOUT_MINUTES = 35
BREAK_DURATION_MINUTES = 15
EXPECTED_VOICES_PER_SHIFT = 15

ADMIN_CHAT_ID = -1002645821302  # <-- id чата руководства!
shift_reports = []

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN)

# --- Фразы со смайликами (по 10 в каждой группе) ---
soviet_phrases = {
    "voice_reminder": [
        "🔔 Товарищ, пора бы уже проговорить текст! 🎤",
        "📢 Эфир ждёт, микрофон скучает! 😴",
        "🎙️ Без голоса — как без хлеба! 🍞",
        "⏰ Напомню нежно — текст в студию! 🎬",
        "📻 Молчание — не золото, а штраф! 🪙",
        "🔊 Время звучать, а не молчать! 🗣️",
        "💬 Эй, ты там? Эфир пустует! 👻",
        "📡 Передай слово в эфир! 📡",
        "🎤 Где твой голос, ведущий?! 🤔",
        "🛎️ Голос — это сигнал. Подай его! 🛎️",
    ],
    "scary_reminder": [
        "😈 Я знаю, где ты живёшь... Не заставляй меня приходить лично! 👀",
        "👹 Ку-ку! Ты ещё жив? Эфир ждёт! Не прячься!",
        "🕷️ Осторожно, паутина тишины затягивает эфир... Срочно голосовое!",
        "🧟‍♂️ Так, если не появишься, ночью тебе приснится эфир!",
        "👾 Я уже рядом... и знаю, что ты не работаешь!",
        "🦉 Я слежу за тобой! Один шаг — и эфир оживёт!",
        "💀 Если не запишешь голосовое, я расскажу начальству твой секрет!",
        "👻 Бууу! Исчезнувших ведущих мы находим быстро. Эфир ждет тебя!",
        "🔪 Не доводи до крайностей! Голосовое — немедленно!",
        "🧙‍♂️ Проклятие молчаливого ведущего уже нависло! Спаси эфир!",
    ],
    "break_acknowledgement": [
        "☕ Хорошо, {username}, перерыв засчитан! Жду обратно в строю!",
        "😎 Принято, {username}, отдыхай. Но не затягивай!",
        "🍔 Конечно, {username}, приятного аппетита!",
        "🕰️ Давай, {username}, но чтобы через 15 минут был как штык!",
        "🥗 Перерыв одобрен, {username}! Главное — вернуться!",
        "🍵 {username}, чай попей, но про эфир не забудь!",
        "🧁 Перерыв — дело святое, возвращайся бодрым, {username}!",
        "🥨 Кофе-пауза включена, {username}, не расслабляйся!",
        "🍫 Сладкий момент, но не задерживайся, {username}!",
        "🍉 Отдыхай, {username}, но эфир всегда на первом месте!",
    ],
    "break_over_reminder": [
        "⏰ Так, перерыв окончен! Где ты, герой эфира? 🦸‍♂️",
        "🚨 Товарищ, пора возвращаться на рабочее место! 🎚️",
        "🤨 Эй, 15 минут давно прошли! Жду в эфире! 📻",
        "🧐 Командование интересуется, не затянулся ли твой отдых? 👀",
        "⏳ Перерыв — это не отпуск! Вернись! 🏃‍♂️",
        "📞 Ждём тебя на связи! Не опаздывай! ⏰",
        "🛑 Время отдыха закончилось — эфир ждёт! 🗣️",
        "📋 План не ждет, возвращайся! 🏁",
        "🚦 Время быть на посту! В эфир! 🚦",
        "🔔 Без ведущего эфир скучает! Возвращайся! 🥲",
    ],
    "scolding": [
        "⚠️ Нужно поднажать, товарищ! 📈",
        "🚩 План не выполняется, усильте работу! 🏃‍♂️",
        "⏱️ Дисциплина хромает, наверстайте упущенное! 🔨",
        "💼 Прошу более ответственно подходить к выполнению обязанностей! 📝",
        "⛔ Такими темпами мы пятилетку не выполним! 🛠️",
        "👀 Руководство уже насторожилось! 😳",
        "🦥 Не тормози, эфир не ждет! 🏎️",
        "🧱 План требует крепких решений! 🪓",
        "🥶 Холодно без твоего голоса, согрей эфир! 🔥",
        "🎯 Цель — эфир, не теряйся! 🧭",
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
    ],
    "return_success": [
        "✅ Товарищ {username}, рад видеть тебя снова на посту! 👋",
        "👍 Отлично, {username}! Ты вернулся вовремя! 🕒",
        "👏 Добро пожаловать обратно, {username}! Продолжаем! 🎧",
        "🎩 Ну вот и снова в эфире, {username}! 🪄",
        "🔙 Ведущий {username} снова в игре! 🏅",
        "🥁 {username} снова с нами — отлично! 🥳",
        "🌞 Рабочий день продолжается, {username}! 💼",
        "🎟️ Ваша смена подтверждена! {username}, вперёд! 🚦",
        "🎬 {username}, камера, мотор — эфир ждёт! 🎥",
        "🕶️ {username}, ты как всегда вовремя! ⏰",
    ],
    "pain_joke": [
        "⏰ Товарищ, если не вернёшься — будет очень и очень больно! (шутка 😜) Или денег не получишь! 💸",
        "⚡ Не затягивай, иначе придётся танцевать на столе! (шутка 😆)",
        "💀 Если не придёшь вовремя — штрафной марш! (шутка 😂)",
        "🥵 Эфир без тебя страдает — возвращайся быстрее! 😄",
        "🩹 Руководство готовит гипс! Вернись! (шутка) 🦴",
        "💸 Премия может уплыть! Возвращайся! 🏊‍♂️",
        "🎲 Не испытывай удачу — эфир ждёт! 🎲",
        "🎻 Без тебя — только тишина! Вернись! 🥲",
        "🎯 Если не придёшь — будешь читать рекламу весь день! (шутка) 📢",
        "🧨 Не доводи до взрыва — возвращайся! 💣",
    ],
    "main_accepted": [
        "🎙️ Товарищ {username} принят как главный на смене! Теперь контроль за эфиром — твой долг. 🫡",
        "🎧 Внимание, {username} — теперь главный по эфиру! Ответственность огромна! 🚦",
        "🪖 {username}, ты принят в смену! Покажи всем класс! 🎼",
        "📡 Новый ведущий в эфире: {username}! Удачи на посту! 🏁",
        "🌅 Смена начинается с тебя, {username}! Вперёд к свершениям! 🏆",
        "🏅 Аплодисменты! {username} — главный на посту! 👏",
        "🛡️ Эфир под твоей защитой, {username} — не подведи! 🔔",
        "👨‍✈️ Ведущий {username} заступил на дежурство! 🚨",
        "🎤 Микрофон твой, {username}! Время действовать! ⏰",
        "🕹️ {username} теперь рулит эфиром! Вперёд! 🏎️",
    ],
    "voice_praise": [
        "🦾 Ай, маладца! Так держать! 👍",
        "🥰 Ой, какой хороший! Эфир доволен! 😁",
        "👏 Вот это работа! Браво! 👏",
        "🤩 Ты снова с нами, супер! 🚀",
        "🥳 Еще одно голосовое! Праздник на эфире! 🎉",
        "😎 Красавчик! Продолжай в том же духе! 🎤",
        "💪 Уважаю старательность! Молодец! 🏅",
        "🕺 Вот это энергия! Эфир оживает! 💃",
        "🧲 Притягиваешь эфир к себе! Супер! 🌟",
        "🍀 Каждый голос — шаг к успеху! Продолжай! 🏆",
    ],
    "too_short": [
        "⏲️ Ой-ой, {username}, это даже не голосовое, а шёпот! Минимум 7 секунд! ⏰",
        "😅 {username}, такой короткий эфир не засчитывается! Продли удовольствие!",
        "🦗 {username}, ну что за жадность на слова? Давай хотя бы 7 секунд!",
        "🔇 {username}, эфир не услышал твоё сообщение! Маловато будет!",
        "🤏 {username}, мало, ещё, ещё! Голосовое должно быть дольше 7 секунд!",
        "😜 {username}, не халтурь, эфир любит длинные тексты!",
        "⏳ {username}, не успел даже чаю налить за это время! Давай длиннее!",
        "🫠 {username}, эфир не засчитал! Минимум 7 секунд!",
        "🦉 {username}, сова не успела проснуться от такого короткого сообщения!",
        "📢 {username}, голосовой — это не пиканье микрофона! Давай по-настоящему!",
    ],
}

welcome_phrases = [
    "👋 Салам, ведущий! Я буду автоматически считать твои голосовые в этом чате. В конце смены отчёт придёт сюда же. 📊",
    "🛰️ На связи, товарищ! Отправляй голосовые в этот чат, и я за всем прослежу. Отчёт будет здесь же, в конце смены. 📑",
    "🚦 Приступаем к работе! В этом чате я твой персональный ревизор: считаю голосовые и слежу за эфиром. 🕵️‍♂️",
    "🎤 Голосовые — твоя сила, а отчёты мои! Дерзай! 💪",
    "📻 Слушаю эфир, подсчитываю успехи! Давай голосовые! 🎙️",
    "📝 Веду дневник эфира! Всё под контролем! 🔎",
    "🎛️ Все кнопки нажаты — поехали! Жду твоих голосовых! 🚦",
    "🧰 Технический контроль активен! Работай на эфир! 🛠️",
    "💼 Отчётность — моё всё! Ты главное — говори! 🗣️",
    "👨‍🔧 Ведущий, я на страже! Считаю твои голосовые! 📈",
]

# --- Ключевые слова для перерыва ---
BREAK_KEYWORDS = [
    "перерыв", "перекур", "покурить", "я на перерыв", "я на обед", "обед", "я кушать",
    "кушать", "ем", "есть", "отдохнуть", "пить", "кофе", "чай", "отойти", "отойду"
]

# --- Хранилище данных ---
chat_data = {}

def is_shift_active():
    now = datetime.datetime.now(moscow_tz)
    if SHIFT_START_HOUR > SHIFT_END_HOUR:
        return now.hour >= SHIFT_START_HOUR or now.hour < SHIFT_END_HOUR
    return SHIFT_START_HOUR <= now.hour < SHIFT_END_HOUR

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
    voice_duration = message.voice.duration

    now = datetime.datetime.now(moscow_tz)
    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'main_username': None, 'users': {}, 'shift_start': now}

    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = {'username': username, 'count': 0, 'reminded': False, 'on_break': False, 'breaks_count': 0, 'late_returns': 0}

    user = users[user_id]

    # --- НЕ ЗАСЧИТЫВАЕМ КОРОТКИЕ ГОЛОСОВЫЕ (<7 сек) ---
    if voice_duration < 7:
        if chat_data[chat_id]['main_id'] == user_id:
            phrase = random.choice(soviet_phrases["too_short"]).format(username=username, seconds=voice_duration)
            bot.send_message(chat_id, phrase)
        return

    user['count'] += 1
    user['last_voice_time'] = now
    user['reminded'] = False

    # Если главного нет, назначаем
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        chat_data[chat_id]['shift_start'] = now
        users[user_id]['last_voice_time'] = now  # Фикс: ставим время для отсчёта бездействия сразу при назначении!
        text = random.choice(soviet_phrases["main_accepted"]).format(username=username)
        bot.send_message(chat_id, text)
    elif chat_data[chat_id]['main_id'] == user_id and user['count'] > 1:
        # Со второго и далее голосового — шутливая похвала
        praise = random.choice(soviet_phrases["voice_praise"])
        bot.send_message(chat_id, praise)

    # Если ведущий возвращается с перерыва
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
    # Не реагировать на пересланные сообщения!
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

@bot.message_handler(commands=["karaoke"])
def karaoke_assign(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    chat_id = message.chat.id
    if not message.text:
        bot.reply_to(message, "📝 Формат: /karaoke @username")
        return
    try:
        cmd, username_tag = message.text.strip().split()
        username = username_tag.strip().lstrip('@')
    except Exception:
        bot.reply_to(message, "📝 Формат: /karaoke @username")
        return
    if chat_id not in chat_data or not chat_data[chat_id]['users']:
        bot.reply_to(message, "🤷‍♂️ Нет данных о пользователях в этом чате.")
        return
    users = chat_data[chat_id]['users']
    uid, userinfo = get_user_by_username(users, f"@{username}")
    if not uid:
        bot.reply_to(message, "❌ Пользователь не найден среди приславших голосовое.")
        return
    chat_data[chat_id]['main_id'] = uid
    chat_data[chat_id]['main_username'] = userinfo['username']
    users[uid]['last_voice_time'] = datetime.datetime.now(moscow_tz)  # Фикс: сброс отсчёта при назначении нового главного!
    bot.send_message(chat_id, f"🎤 Теперь товарищ {userinfo['username']} — главный на смене! 🫡")

def get_reminder_phrase():
    # 80% обычные, 20% устрашающие
    if random.random() < 0.2:
        return random.choice(soviet_phrases["scary_reminder"])
    else:
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

        # Проверка перерыва
        if user.get('on_break'):
            minutes_on_break = (now - user['break_start_time']).total_seconds() / 60
            if minutes_on_break > BREAK_DURATION_MINUTES and not user.get('reminded'):
                try:
                    phrase = random.choice(soviet_phrases["pain_joke"])
                    bot.send_message(chat_id, phrase)
                    user['reminded'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о конце перерыва: {e}")
            continue

        # Проверка бездействия
        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES and not user.get('reminded'):
                try:
                    phrase = get_reminder_phrase()
                    bot.send_message(chat_id, phrase)
                    user['reminded'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание: {e}")

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    welcome_message = random.choice(welcome_phrases)
    bot.reply_to(message, welcome_message)

@bot.message_handler(commands=["промежуточный", "promezhut"])
def send_interim_report(message):
    if message.chat.id == ADMIN_CHAT_ID:
        return
    chat_id = message.chat.id
    if chat_id not in chat_data:
        bot.send_message(chat_id, "Нет данных по смене в этом чате.")
        return

    data = chat_data[chat_id]
    main_id = data.get('main_id')
    users = data.get('users', {})
    main_user = users.get(main_id)

    if not main_user:
        bot.send_message(chat_id, "Главный ведущий ещё не назначен.")
        return

    breaks_count = main_user.get('breaks_count', 0)
    late_returns = main_user.get('late_returns', 0)
    said_count = main_user.get('count', 0)
    perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100)
    username = main_user.get('username', 'Неизвестно')

    report_lines = [
        f"📋 #Промежуточный_отчет ({data['shift_start'].strftime('%d.%m.%Y')})",
        f"🎤 Ведущий: {username}",
        f"🗣️ Голосовых: {said_count} из {EXPECTED_VOICES_PER_SHIFT} ({perc}%)",
        f"☕ Перерывов: {breaks_count}",
        f"⏳ Задержек после перерыва: {late_returns}",
    ]

    bot.send_message(chat_id, "\n".join(report_lines))

def send_end_of_shift_reports():
    now = datetime.datetime.now(moscow_tz)
    report_date = chat_data[list(chat_data)[0]]['shift_start'].strftime("%d.%m.%Y") if chat_data else now.strftime("%d.%m.%Y")

    for chat_id, data in chat_data.items():
        users = data.get('users')
        main_id = data.get('main_id')
        main_user = users.get(main_id)
        if not main_user:
            continue

        breaks_count = main_user.get('breaks_count', 0)
        late_returns = main_user.get('late_returns', 0)
        said_count = main_user.get('count', 0)
        perc = round(said_count / EXPECTED_VOICES_PER_SHIFT * 100)
        praise = ""
        if perc >= 80:
            praise = "\n\n" + random.choice(soviet_phrases["praise"])
        elif perc >= 50:
            praise = "\n\n" + random.choice(soviet_phrases["scolding"])
        elif perc < 50:
            praise = "\n\n⚠️ Смена провалена, эфир был слишком тихим!"

        report_lines = [
            f"📋 #Отчет_Текст_Ведущего ({data['shift_start'].strftime('%d.%m.%Y')})",
            f"🏢 Чат: {bot.get_chat(chat_id).title if hasattr(bot.get_chat(chat_id), 'title') else chat_id}",
            f"🎤 Ведущий: {main_user['username']}",
            f"🗣️ Всего голосовых: {said_count} из {EXPECTED_VOICES_PER_SHIFT}",
            f"☕ Перерывов: {breaks_count}",
            f"⏳ Задержек после перерыва: {late_returns}",
            praise
        ]
        final_report = "\n".join([line for line in report_lines if line.strip()])
        try:
            bot.send_message(chat_id, final_report)
        except Exception as e:
            logging.error(str(e))

        try:
            chat_title = bot.get_chat(chat_id).title if hasattr(bot.get_chat(chat_id), 'title') else str(chat_id)
        except:
            chat_title = str(chat_id)
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
        # Извлекаем данные для анализа
        lines = item["report"].splitlines()
        said_count = 0
        expected = EXPECTED_VOICES_PER_SHIFT
        late_returns = 0
        for line in lines:
            if "Всего голосовых" in line:
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
    # Можно вызвать в любом чате: отчёт уйдёт и в чат, и руководству
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
