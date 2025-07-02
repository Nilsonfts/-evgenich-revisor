# main.py
import telebot
import threading
import logging
from typing import Dict, List

# === Импорты из внутренних модулей ===
from config import BOT_TOKEN, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE
from state import chat_configs, ad_templates
from utils import load_json_data
from handlers import register_handlers
from scheduler import run_scheduler

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# === Инициализация бота ===
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# === Загрузка всех данных при старте ===
def load_all_data():
    chat_configs.update({int(k): v for k, v in load_json_data(CHAT_CONFIG_FILE, {}).items()})
    ad_templates.update(load_json_data(AD_TEMPLATES_FILE, {}))
    logging.info(f"Загружено {len(chat_configs)} конфигураций чатов.")

# === Точка входа ===
if __name__ == "__main__":
    logging.info("🎙️ Запуск Telegram-бота...")
    
    # 1. Загружаем данные
    load_all_data()
    
    # 2. Регистрируем все обработчики
    register_handlers(bot)
    logging.info("✅ Обработчики успешно зарегистрированы.")
    
    # 3. Запускаем планировщик в отдельном фоновом потоке
    scheduler_thread = threading.Thread(target=run_scheduler, args=(bot,), daemon=True)
    scheduler_thread.start()
    logging.info("⏰ Планировщик запущен в фоновом режиме.")
    
    # 4. Запускаем основную работу бота (прослушивание сообщений)
    logging.info("🚀 Бот готов к работе и слушает сообщения.")
    bot.infinity_polling(timeout=60, long_polling_timeout=40)
