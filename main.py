# main.py
import telebot
import threading
import logging
import json
from dataclasses import asdict

# === Импорты из внутренних модулей ===
from config import BOT_TOKEN, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE
from state import chat_configs, ad_templates, chat_data, user_history
from utils import load_json_data
from handlers import register_handlers # ИЗМЕНЕНО: Импортируем из пакета handlers
from scheduler import run_scheduler
from state_manager import load_state
from models import ShiftData, UserData # ИМПОРТИРУЕМ НАШИ МОДЕЛИ

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# === Кастомный JSON-энкодер для сохранения dataclasses ===
class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, '__dataclass_fields__'):
            return asdict(o)
        return super().default(o)

# === Инициализация бота ===
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown", json_encoder=EnhancedJSONEncoder)

# === Загрузка всех данных при старте ===
def load_all_data():
    """Загружает все постоянные и временные данные при старте бота."""
    global chat_data, user_history # Объявляем, что будем изменять глобальные переменные
    
    # Загружаем постоянные конфигурации
    raw_configs = load_json_data(CHAT_CONFIG_FILE, {})
    # Конвертируем ключи в int, так как chat_id - это число
    chat_configs.update({int(k): v for k, v in raw_configs.items()})
    
    ad_templates.update(load_json_data(AD_TEMPLATES_FILE, {}))
    logging.info(f"Загружено {len(chat_configs)} конфигураций чатов.")

    # Загружаем состояние и конвертируем словари в dataclasses
    loaded_chat_data_raw, loaded_user_history_raw = load_state()
    
    temp_chat_data = {}
    for chat_id, shift_dict in loaded_chat_data_raw.items():
        users_in_shift = {int(uid): UserData(**udict) for uid, udict in shift_dict.get('users', {}).items()}
        shift_dict['users'] = users_in_shift
        temp_chat_data[int(chat_id)] = ShiftData(**shift_dict)
    
    chat_data = temp_chat_data
    user_history = loaded_user_history_raw

    if loaded_chat_data_raw:
        logging.info(f"Восстановлено {len(chat_data)} активных смен из файла.")


# === Запуск фонового планировщика ===
def start_background_tasks():
    """Запускает планировщик в отдельном потоке."""
    threading.Thread(target=run_scheduler, args=(bot,), daemon=True).start()

# === Точка входа ===
if __name__ == "__main__":
    load_all_data()
    register_handlers(bot) # ИЗМЕНЕНО: Вызываем единую функцию регистрации
    start_background_tasks()
    
    logging.info("Бот запущен и готов к работе.")
    bot.polling(none_stop=True)
