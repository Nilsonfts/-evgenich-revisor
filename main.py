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
from database_manager import db  # Новый database manager

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
    try:
        # Проверяем подключение к базе данных
        db_status = "connected"
        try:
            # Пытаемся выполнить простой запрос к БД
            if hasattr(db, 'test_connection'):
                db.test_connection()
            else:
                # Fallback тест
                db.get_user_stats(123456)  # Простой тест запрос
        except Exception as db_error:
            logging.warning(f"Database test failed: {db_error}")
            db_status = "disconnected"
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "bot_running": True,
            "database": db_status
        }
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, 503

@health_app.route('/')
def root_check():
    """Root endpoint для Railway (на случай если Railway проверяет корень)."""
    return health_check()

def run_health_server():
    """Запускает health check сервер в отдельном потоке."""
    try:
        port = int(os.environ.get('PORT', 8000))  # Изменяем на 8000
        logging.info(f"🌐 Запуск health сервера на порту {port}")
        health_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logging.error(f"❌ Ошибка запуска health сервера: {e}")
        raise

# === Загрузка всех данных при старте ===
def load_all_data():
    """Загружает все постоянные и временные данные при старте бота."""
    global chat_data, user_history
    
    raw_configs = load_json_data(CHAT_CONFIG_FILE, {})
    chat_configs.update({str(k): v for k, v in raw_configs.items()})  # Всегда строковые ключи
    
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
    try:
        logging.info("🚀 Начинаем запуск бота ЕВГЕНИЧ...")
        
        # Загружаем данные
        load_all_data()
        logging.info("✅ Данные загружены")
        
        # Тестируем подключение к базе данных
        try:
            db.test_connection()
            logging.info("✅ Подключение к базе данных успешно")
        except Exception as db_error:
            logging.warning(f"⚠️ Проблема с базой данных: {db_error}")
        
        # Регистрируем обработчики
        handlers.register_handlers(bot)  # Регистрируем модульные обработчики (включая wizards)
        register_admin_panel_handlers(bot)  # Регистрируем админ-панель (кнопочное меню)
        logging.info("✅ Обработчики зарегистрированы")
        
        # Регистрируем команды бота для подсказок в Telegram
        try:
            from telebot import types as tg_types
            bot.set_my_commands([
                tg_types.BotCommand("start", "🚀 Начать смену"),
                tg_types.BotCommand("check", "📋 Промежуточный отчет"),
                tg_types.BotCommand("gameover", "🏁 Завершить смену"),
                tg_types.BotCommand("help", "📖 Справка"),
                tg_types.BotCommand("admin", "⚜️ Панель администратора"),
                tg_types.BotCommand("status", "📊 Статус системы"),
                tg_types.BotCommand("rating", "🏆 Рейтинг ведущих"),
                tg_types.BotCommand("time", "🕐 Текущее время"),
                tg_types.BotCommand("pause", "⏸️ Пауза (40 мин)"),
                tg_types.BotCommand("stop_pause", "⏯️ Завершить паузу"),
                tg_types.BotCommand("settings", "⚙️ Настройки чата"),
                tg_types.BotCommand("roles", "🎭 Информация о ролях"),
            ])
            logging.info("✅ Команды бота зарегистрированы")
        except Exception as cmd_err:
            logging.warning(f"⚠️ Не удалось установить команды бота: {cmd_err}")
        
        # Запускаем фоновые задачи
        start_background_tasks()
        logging.info("✅ Планировщик запущен")
        
        # Запускаем health check сервер (ВАЖНО: запускаем первым для Railway)
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        logging.info("✅ Health check сервер запущен")
        
        # Даем время серверу запуститься
        import time
        time.sleep(2)
        
        logging.info("🎯 Бот запущен и готов к работе!")
        
        # Graceful shutdown — сохраняем состояние при остановке
        import signal
        from state_manager import save_state
        
        def graceful_shutdown(signum, frame):
            logging.info("🛑 Получен сигнал завершения. Сохраняю состояние...")
            try:
                save_state(bot, chat_data, user_history)
                logging.info("✅ Состояние сохранено")
            except Exception as e:
                logging.error(f"❌ Ошибка сохранения: {e}")
            logging.info("👋 Бот остановлен")
            exit(0)
        
        signal.signal(signal.SIGTERM, graceful_shutdown)
        signal.signal(signal.SIGINT, graceful_shutdown)
        
        # Запускаем polling бота
        bot.polling(none_stop=True)
        
    except Exception as e:
        logging.error(f"❌ Критическая ошибка при запуске: {e}")
        raise
