import logging
import os
import telebot
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telebot import types
import json
import pytz  # Библиотека для работы с часовыми поясами, ее нужно установить

# --- Настройки и авторизация (без изменений) ---
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

bot = telebot.TeleBot(BOT_TOKEN)

# --- Ваш словарь с фразами (остается без изменений) ---
soviet_phrases = {
    "report": [
        "✅ Принято! Доклад блестящий!",
        "📈 Отчёт принят, как тост на банкете!",
        "🗂️ Всё внесено. Молодец!",
        "📋 Система довольна твоей дисциплиной.",
        "🧾 Зафиксировано в летописях рабочего дня.",
        "📊 Данные занесены. Профсоюз одобрит.",
        "🔍 В отчёте всё чётко. Хорошо поработал!",
        "✏️ Бумага стерпела — и таблица тоже.",
        "🕮 Зарегистрировано. Работа идёт!",
        "📎 Вклад отмечен. Ты надёжен, как токарь!",
        "📓 Отчёт выглядит достойно.",
        "📌 Принято и проверено. Всё по уставу!",
        "🔖 Лог обновлён. Товарищи довольны!",
        "📘 Архив пополнился свежей строкой.",
        "📚 Бумаги летают, отчёт готов!",
        "🔐 Дело сделано, запись сохранена!",
        "📨 Принято. Информация ушла в хронику!",
        "💼 Всё по регламенту. Спасибо!",
        "🖇️ Скреплено и заархивировано!",
        "📅 Ежедневный подвиг зафиксирован."
    ]
    # ... и другие ваши списки фраз ...
}

# --- Хранилище для подсчета голосовых сообщений ---
# Этот словарь будет хранить данные в формате {id_пользователя: количество_сообщений}
# ВАЖНО: При перезапуске бота эти данные сбросятся.
voice_counts = {}

# --- Обработчик для автоматического подсчета голосовых сообщений ---
@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    # Увеличиваем счетчик для этого пользователя
    current_count = voice_counts.get(user_id, 0) + 1
    voice_counts[user_id] = current_count

    logging.info(f"Засчитано голосовое сообщение от {username}. Текущий счет: {current_count}")


# --- Основные команды бота ---
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(message, "Салам, ведущий! Я буду автоматически считать твои голосовые сообщения. Когда понадобится, используй команду /отчет.")

@bot.message_handler(commands=["отчет"])
def handle_report(message):
    try:
        user_id = message.from_user.id
        user = message.from_user
        username = f"@{user.username}" if user.username else user.first_name

        # Получаем количество посчитанных голосовых. Если их не было, вернется 0.
        facts = voice_counts.get(user_id, 0)

        # Здесь вы можете решить, что делать со вторым числом. Пока оставим его пустым.
        could_be = ""  # Или можете поставить "5", "10" или любое другое значение

        # Устанавливаем московский часовой пояс
        moscow_tz = pytz.timezone("Europe/Moscow")
        now = datetime.datetime.now(moscow_tz).strftime("%d.%m.%Y")

        phrase = soviet_phrases["report"][hash(user_id) % len(soviet_phrases["report"])]

        # Создаем строку для записи в таблицу
        row = [f"#{now}", username, str(facts), could_be, phrase]

        # Записываем данные и отправляем подтверждение
        sheet.append_row(row)
        logging.info(f"Добавлен отчет: {row}")
        bot.reply_to(message, f"{phrase}\nЗаписано в журнал **{facts}** голосовых за {now}.")

        # Обнуляем счетчик для этого пользователя после успешного отчета
        voice_counts[user_id] = 0
        logging.info(f"Счетчик для {username} сброшен.")

    except Exception as e:
        logging.error(f"Ошибка при создании отчета: {e}")
        bot.reply_to(message, "Товарищ, при создании отчета произошла непредвиденная ошибка!")

# --- Запуск бота ---
if __name__ == '__main__':
    logging.info("Бот запущен...")
    bot.polling(none_stop=True)
