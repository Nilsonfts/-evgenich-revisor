# main.py
import telebot
import threading
import logging
from typing import Dict, List

# Импортируем все необходимое из наших новых файлов
from config import BOT_TOKEN
from state import chat_configs, ad_templates
from utils import load_json_data
from handlers import register_handlers
from scheduler import run_scheduler

# --- Инициализация ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

def load_all_data():
    """Загружает все данные из JSON файлов при старте."""
    from config import CHAT_CONFIG_FILE, AD_TEMPLATES_FILE
    # Обратите внимание: мы явно передаем словари для их изменения
    chat_configs.update({int(k): v for k, v in load_json_data(CHAT_CONFIG_FILE, {}).items()})
    ad_templates.update(load_json_data(AD_TEMPLATES_FILE, {}))
    logging.info(f"Загружено {len(chat_configs)} конфигов чатов и {len(ad_templates)} брендов с шаблонами.")

# --- Основной блок запуска ---
if __name__ == '__main__':
    logging.info("🤖 Бот запускается...")

    # 1. Загружаем данные
    load_all_data()

    # 2. Регистрируем все обработчики, передавая им объект бота
    register_handlers(bot)
    logging.info("✅ Обработчики успешно зарегистрированы.")

    # 3. Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, args=(bot,), daemon=True)
    scheduler_thread.start()
    logging.info("⏰ Планировщик запущен.")

    # 4. Запускаем бота
    logging.info("🚀 Бот готов к работе.")
    bot.infinity_polling(timeout=60)
