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

moscow_tz = pytz.timezone("Europe/Moscow")
bot = telebot.TeleBot(BOT_TOKEN)

soviet_phrases = {
    "voice_reminder": [
        "🔔 Товарищ, пора бы уже проговорить текст!",
        "📢 Эфир ждёт, микрофон скучает!",
        "🎙️ Без голоса — как без хлеба!",
        "⏰ Напомню нежно — текст в студию!",
    ],
    "break_acknowledgement": [
        "Хорошо, даю перерыв. Жду обратно в строю!",
        "Принято, отдыхай. Но не затягивай!",
        "Конечно, товарищ. Приятного аппетита!",
        "Давай, но чтоб через 15 минут был как штык!",
    ],
    "break_over_reminder": [
        "Так, перерыв окончен! Где ты, герой эфира?",
        "Товарищ, пора возвращаться на рабочее место!",
        "Эй, 15 минут давно прошли! Жду в эфире!",
        "Командование интересуется, не затянулся ли твой отдых?",
    ],
}

# --- Хранилище данных ---
# { chat_id: { main_id: user_id, main_username: username, users: {user_id: {username:..., ...}} } }
chat_data = {}

# --- Вспомогательные функции ---
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

# --- Обработка голосовых ---
@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)

    if chat_id not in chat_data:
        chat_data[chat_id] = {'main_id': None, 'main_username': None, 'users': {}}

    users = chat_data[chat_id]['users']
    if user_id not in users:
        users[user_id] = {'username': username, 'count': 0, 'reminded': False, 'on_break': False}

    users[user_id]['count'] += 1
    users[user_id]['last_voice_time'] = datetime.datetime.now(moscow_tz)
    users[user_id]['reminded'] = False

    # Если главного нет, назначаем, иначе игнорируем
    if chat_data[chat_id]['main_id'] is None:
        chat_data[chat_id]['main_id'] = user_id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"🎙️ Товарищ {username} принят как главный на смене! Теперь контроль за эфиром — твой долг.")

    logging.info(f"Голосовое от {username} в чате {chat_id}. Всего: {users[user_id]['count']}")

    # Если ведущий возвращается с перерыва
    if users[user_id].get('on_break'):
        users[user_id]['on_break'] = False
        bot.send_message(chat_id, f"Товарищ {username}, рад видеть тебя снова на посту!")

# --- Перерыв ---
@bot.message_handler(func=lambda m: m.text and any(word in m.text.lower() for word in ["курить", "перерыв", "есть", "пить", "отойду"]))
def handle_break_request(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = get_username(message)

    if chat_id not in chat_data or chat_data[chat_id].get('main_id') != user_id:
        bot.reply_to(message, "Перерыв можно брать только главному на смене!")
        return

    user = chat_data[chat_id]['users'][user_id]
    user['on_break'] = True
    user['break_start_time'] = datetime.datetime.now(moscow_tz)
    ack = random.choice(soviet_phrases["break_acknowledgement"])
    bot.reply_to(message, ack)

# --- Сброс смены ---
@bot.message_handler(commands=["restart"])
def restart_main(message):
    chat_id = message.chat.id
    if chat_id in chat_data:
        chat_data[chat_id]['main_id'] = None
        chat_data[chat_id]['main_username'] = None
        # Сохраняем пользователей, но сбрасываем главного
        bot.send_message(chat_id, "Смена перезапущена. Жду нового голосового для назначения главного!")

# --- Назначение по команде /karaoke @username ---
@bot.message_handler(commands=["karaoke"])
def karaoke_assign(message):
    chat_id = message.chat.id
    if not message.text:
        bot.reply_to(message, "Формат: /karaoke @username")
        return
    try:
        cmd, username_tag = message.text.strip().split()
        username = username_tag.strip().lstrip('@')
    except Exception:
        bot.reply_to(message, "Формат: /karaoke @username")
        return
    if chat_id not in chat_data or not chat_data[chat_id]['users']:
        bot.reply_to(message, "Нет данных о пользователях в этом чате.")
        return
    users = chat_data[chat_id]['users']
    uid, userinfo = get_user_by_username(users, f"@{username}")
    if not uid:
        bot.reply_to(message, "Пользователь не найден среди приславших голосовое.")
        return
    chat_data[chat_id]['main_id'] = uid
    chat_data[chat_id]['main_username'] = userinfo['username']
    bot.send_message(chat_id, f"Теперь товарищ {userinfo['username']} — главный на смене!")

# --- Напоминания и проверка активности ---
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
            if minutes_on_break > BREAK_DURATION_MINUTES:
                try:
                    phrase = random.choice(soviet_phrases["break_over_reminder"])
                    bot.send_message(main_id, phrase)
                    user['on_break'] = False
                    user['last_voice_time'] = now
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о конце перерыва: {e}")
            continue

        # Проверка бездействия
        if 'last_voice_time' in user:
            minutes_passed = (now - user['last_voice_time']).total_seconds() / 60
            if minutes_passed > VOICE_TIMEOUT_MINUTES and not user.get('reminded'):
                try:
                    phrase = random.choice(soviet_phrases["voice_reminder"])
                    bot.send_message(main_id, f"{phrase}\n(Это напоминание только главному на смене — {user['username']})")
                    user['reminded'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание: {e}")

def run_scheduler():
    schedule.every(1).minutes.do(check_users_activity)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    logging.info("Бот запущен. Ожидание голосовых для назначения главного на смене...")
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    bot.polling(none_stop=True)
