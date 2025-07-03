# main.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)
import telebot
import threading
import logging
from typing import Dict, List

# === Импорты из внутренних модулей ===
from config import BOT_TOKEN, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE
from state import chat_configs, ad_templates, chat_data, user_history
from utils import load_json_data
from handlers import register_handlers
from scheduler import run_scheduler
from state_manager import load_state # <--- НОВЫЙ ИМПОРТ

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
    """Загружает все постоянные и временные данные при старте бота."""
    # Загружаем постоянные конфигурации
    chat_configs.update({int(k): v for k, v in load_json_data(CHAT_CONFIG_FILE, {}).items()})
    ad_templates.update(load_json_data(AD_TEMPLATES_FILE, {}))
    logging.info(f"Загружено {len(chat_configs)} конфигураций чатов.")

    # ИСПРАВЛЕНО: Загружаем состояние активных смен и истории
    loaded_chat_data, loaded_user_history = load_state()
    chat_data.update(loaded_chat_data)
    user_history.update(loaded_user_history)
    if loaded_chat_data:
        logging.info(f"Восстановлено {len(loaded_chat_data)} активных смен из файла.")


# === Запуск фонового планировщика ===
def start_background_tasks():
    """Запускает планировщик в отдельном потоке."""
    threading.Thread(target=run_scheduler, args=(bot,), daemon=True).start()

# === Точка входа ===
if __name__ == "__main__":
    load_all_data()
    register_handlers(bot)
    start_background_tasks()
    
    logging.info("Бот запущен и готов к работе.")
    bot.polling(none_stop=True)
