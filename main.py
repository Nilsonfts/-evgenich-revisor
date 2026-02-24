# main.py
import threading
import logging
import json
import os
import time
from flask import Flask
from datetime import datetime

# === Настройка логирования (ПЕРВЫМ!) ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# === Health check для Railway (запускаем ДО всех тяжёлых импортов) ===
health_app = Flask(__name__)
_bot_ready = False

@health_app.route('/health')
def health_check():
    return {
        "status": "healthy" if _bot_ready else "starting",
        "timestamp": datetime.now().isoformat(),
        "bot_ready": _bot_ready
    }, 200

@health_app.route('/')
def root_check():
    return health_check()

def run_health_server():
    try:
        port = int(os.environ.get('PORT', 8080))
        logging.info(f"🌐 Запуск health сервера на порту {port}")
        health_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logging.error(f"❌ Ошибка запуска health сервера: {e}")
        raise

# Глобальная переменная (для from main import bot)
bot = None

# === Точка входа ===
if __name__ == "__main__":
    try:
        logging.info("🚀 Начинаем запуск бота ЕВГЕНИЧ...")

        # ШАГ 1: Запускаем health check сервер ПЕРВЫМ для Railway
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        time.sleep(1)
        logging.info("✅ Health check сервер запущен")

        # ШАГ 2: Импортируем тяжёлые модули (БД, хендлеры и т.д.)
        import telebot
        from telebot import types as tg_types
        from dataclasses import asdict
        from config import BOT_TOKEN, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE
        from state import chat_configs, ad_templates, chat_data, user_history, data_lock
        from utils import load_json_data
        import handlers
        from admin_panel import register_admin_panel_handlers
        from scheduler import run_scheduler
        from state_manager import load_state
        from models import ShiftData, UserData
        from database_manager import db
        logging.info("✅ Все модули импортированы")

        # ШАГ 3: Инициализация бота
        if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
            logging.error("❌ Токен бота не настроен!")
            exit(1)
        if ":" not in BOT_TOKEN:
            logging.error("❌ Неверный формат токена бота!")
            exit(1)

        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
        logging.info("✅ Бот инициализирован")

        # ШАГ 4: Загружаем данные
        raw_configs = load_json_data(CHAT_CONFIG_FILE, {})
        chat_configs.update({str(k): v for k, v in raw_configs.items()})
        ad_templates.update(load_json_data(AD_TEMPLATES_FILE, {}))
        logging.info(f"Загружено {len(chat_configs)} конфигураций чатов.")

        loaded_chat_data_raw, loaded_user_history_raw = load_state()
        temp_chat_data = {}
        for cid, shift_dict in loaded_chat_data_raw.items():
            try:
                users_in_shift = {int(uid): UserData(**udict) for uid, udict in shift_dict.get('users', {}).items()}
                shift_dict['users'] = users_in_shift
                temp_chat_data[int(cid)] = ShiftData(**shift_dict)
            except (TypeError, KeyError) as e:
                logging.error(f"Ошибка данных чата {cid}: {e}. Пропускаем...")
                continue
        with data_lock:
            chat_data.clear()
            chat_data.update(temp_chat_data)
            user_history.clear()
            user_history.update(loaded_user_history_raw)
        if chat_data:
            logging.info(f"Восстановлено {len(chat_data)} активных смен.")
        logging.info("✅ Данные загружены")

        # ШАГ 5: Тестируем подключение к БД
        try:
            db.test_connection()
            logging.info("✅ Подключение к базе данных успешно")
        except Exception as db_error:
            logging.warning(f"⚠️ Проблема с базой данных: {db_error}")

        # ШАГ 6: Регистрируем обработчики
        handlers.register_handlers(bot)
        register_admin_panel_handlers(bot)
        logging.info("✅ Обработчики зарегистрированы")

        # ШАГ 7: Команды бота
        try:
            bot.set_my_commands([
                tg_types.BotCommand("start", "🚀 На смену, воин!"),
                tg_types.BotCommand("check", "📋 Как мои дела?"),
                tg_types.BotCommand("gameover", "🏁 Хватит, я устал"),
                tg_types.BotCommand("help", "📖 Что тут вообще можно?"),
                tg_types.BotCommand("admin", "⚜️ Я тут главный"),
                tg_types.BotCommand("status", "📊 Что происходит?"),
                tg_types.BotCommand("rating", "🏆 Кто сегодня молодец?"),
                tg_types.BotCommand("time", "🕐 Сколько натикало?"),
                tg_types.BotCommand("pause", "⏸️ Тишина на 40 мин"),
                tg_types.BotCommand("stop_pause", "⏯️ Хватит тишины"),
                tg_types.BotCommand("settings", "⚙️ Настройки чата"),
                tg_types.BotCommand("roles", "🎭 Кто кем работает?"),
                tg_types.BotCommand("commands", "📋 Все команды"),
            ])
            logging.info("✅ Команды бота зарегистрированы")
        except Exception as cmd_err:
            logging.warning(f"⚠️ Не удалось установить команды бота: {cmd_err}")

        # ШАГ 8: Фоновые задачи
        threading.Thread(target=run_scheduler, args=(bot,), daemon=True).start()
        logging.info("✅ Планировщик запущен")

        # Бот готов
        _bot_ready = True
        logging.info("🎯 Бот запущен и готов к работе!")

        # Graceful shutdown
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
        import traceback
        traceback.print_exc()
        # Держим процесс живым чтобы видеть логи и healthcheck в Railway
        logging.info("⏳ Процесс остаётся запущенным для диагностики...")
        while True:
            time.sleep(60)
