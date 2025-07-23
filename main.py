# main.py
import telebot
import threading
import logging
import json
import os
from dataclasses import asdict
from flask import Flask
from datetime import datetime

# === Импорты из внутренних модулей ===
from config import BOT_TOKEN, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE
from state import chat_configs, ad_templates, chat_data, user_history, data_lock
from utils import load_json_data
import handlers
from admin_panel import register_admin_panel_handlers
from scheduler import run_scheduler
from state_manager import load_state
from models import ShiftData, UserData

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
# ИЗМЕНЕНО: Убран аргумент json_encoder, чтобы обеспечить совместимость
# === Инициализация бота с проверкой токена ===
if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
    logging.error("❌ Токен бота не настроен! Отредактируйте файл .env")
    exit(1)

# Проверяем формат токена
if ":" not in BOT_TOKEN:
    logging.error("❌ Неверный формат токена бота! Токен должен содержать ':'")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Health check для Railway
health_app = Flask(__name__)

@health_app.route('/health')
def health_check():
    """Health check endpoint для Railway."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_running": True
    }

def run_health_server():
    """Запускает health check сервер в отдельном потоке."""
    try:
        port = int(os.environ.get('PORT', 8081))
        logging.info(f"Запуск health сервера на порту {port}")
        health_app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logging.error(f"Ошибка запуска health сервера: {e}")

# === Загрузка всех данных при старте ===
def load_all_data():
    """Загружает все постоянные и временные данные при старте бота."""
    global chat_data, user_history
    
    raw_configs = load_json_data(CHAT_CONFIG_FILE, {})
    chat_configs.update({int(k): v for k, v in raw_configs.items()})
    
    ad_templates.update(load_json_data(AD_TEMPLATES_FILE, {}))
    logging.info(f"Загружено {len(chat_configs)} конфигураций чатов.")

    loaded_chat_data_raw, loaded_user_history_raw = load_state()
    
    temp_chat_data = {}
    for chat_id, shift_dict in loaded_chat_data_raw.items():
        try:
            users_in_shift = {int(uid): UserData(**udict) for uid, udict in shift_dict.get('users', {}).items()}
            shift_dict['users'] = users_in_shift
            temp_chat_data[int(chat_id)] = ShiftData(**shift_dict)
        except (TypeError, KeyError) as e:
            logging.error(f"Ошибка при конвертации данных для чата {chat_id}: {e}. Пропускаем...")
            continue
    
    with data_lock:
        chat_data.clear()
        chat_data.update(temp_chat_data)
        user_history.clear()
        user_history.update(loaded_user_history_raw)

    if chat_data:
        logging.info(f"Восстановлено {len(chat_data)} активных смен из файла.")


# === Запуск фонового планировщика ===
def start_background_tasks():
    """Запускает планировщик в отдельном потоке."""
    threading.Thread(target=run_scheduler, args=(bot,), daemon=True).start()

# === Точка входа ===
if __name__ == "__main__":
    load_all_data()
    # Сначала регистрируем модульные обработчики из handlers/
    handlers.register_handlers(bot)  # Регистрируем модульные обработчики (включая wizards)
    register_admin_panel_handlers(bot)  # Регистрируем админ-панель
    start_background_tasks()
    threading.Thread(target=run_health_server, daemon=True).start()  # Запускаем health check сервер
    
    logging.info("Бот запущен и готов к работе.")
    bot.polling(none_stop=True)
