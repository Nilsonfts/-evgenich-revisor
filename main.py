import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import openai

# Загружаем переменные окружения из .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Проверка наличия токенов
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")
if not OPENAI_API_KEY:
    raise ValueError("Переменная окружения OPENAI_API_KEY не установлена!")

openai.api_key = OPENAI_API_KEY

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Я готов работать ассистентом! Напиши /help для списка функций.")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "Я умею:\n"
        "/start — Запуск\n"
        "/help — Помощь\n"
        "/ask вопрос — Ответ от GPT\n\n"
        "Пример: /ask Как приготовить чебурек?"
    )

@dp.message(Command("ask"))
async def ask_gpt(message: types.Message):
    prompt = message.text.replace("/ask", "").strip()
    if not prompt:
        await message.answer("Напиши вопрос после /ask, например:\n/ask Как устроен телеграм-бот?")
        return
    await message.answer("Секунду, думаю... 🤔")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Можно указать "gpt-4o" или "gpt-4" если доступно
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        gpt_answer = response["choices"][0]["message"]["content"]
        await message.answer(gpt_answer)
    except Exception as e:
        await message.answer(f"Ошибка при обращении к GPT:\n{e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
