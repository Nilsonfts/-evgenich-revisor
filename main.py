import logging
import os
import telebot
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telebot import types

# Настройка логгера
logging.basicConfig(level=logging.INFO)

# Переменные окружения (для Railway или локально)
BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Авторизация Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

bot = telebot.TeleBot(BOT_TOKEN)

soviet_phrases = {
    "check_in": [
        "📻 На смену заступил, как на передовую!",
        "🕰️ На месте. Работаем по графику, как электропоезд.",
        "🔧 Прибыл. Буду бдить и контролировать.",
        "💂‍♂️ В строю. Готов нести службу Родине и делу.",
        "🧰 На посту, инструменты при мне!",
    ],
    "voice_reminder": [
        "🔔 Товарищ, не пора ли проговорить текст?",
        "📢 Ваш голос нужен эфирному фронту!",
        "🎙️ Голосовая пауза затянулась. Действуйте!",
        "⏰ Эфир ждёт. Пора в бой!",
        "📻 Где звук? Где речь? Родина ждёт эфира!",
    ],
    "break_warn": [
        "☕ Перерыв понятен, но не затягивайся!",
        "📌 Уже 15 минут — пора возвращаться в строй.",
        "📯 Командование интересуется, где ты, герой?",
        "🕵️‍♂️ Засиделся! Работа сама себя не сделает.",
        "🚨 Возвращайся, пока не начался разбор полётов!",
    ],
    "report": [
        "Отчёт принят. Работа идёт, фронт стабилен.",
        "Ваш вклад в дело — на высоте. Принято.",
        "📈 Документ зарегистрирован. Вы — опора коллектива.",
        "🗂️ Запись внесена. Продолжайте в том же духе!",
        "✅ Принято. Систематично и исполнительно!",
    ]
}

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(message, "Салам, ведущий! Используй /отчет чтобы внести свой вклад в славную таблицу.")

@bot.message_handler(commands=["отчет"])
def handle_report(message):
    user = message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    now = datetime.datetime.now().strftime("%d.%m.%Y")
    phrase = soviet_phrases["report"][hash(user.id) % len(soviet_phrases["report"])]

    # Заглушка чисел — по-хорошему, должны спрашиваться
    facts = "3"
    could_be = "5"

    row = [f"#{now}", username, facts, could_be, phrase]
    sheet.append_row(row)
    bot.reply_to(message, f"{phrase}\nЗаписано в журнал за {now}")

bot.polling()
