# state_manager.py
import json
import logging
import os

# ИЗМЕНЕНО: Пути теперь ведут в папку 'data'
CHAT_DATA_FILE = 'data/chat_data.json'
USER_HISTORY_FILE = 'data/user_history.json'
STATE_FILES = {
    'chat_data': CHAT_DATA_FILE,
    'user_history': USER_HISTORY_FILE
}

def save_state(chat_data: dict, user_history: dict):
    """Сохраняет текущее состояние chat_data и user_history в JSON-файлы."""
    logging.info("Сохранение состояния бота...")
    
    # Убедимся, что директория 'data' существует
    os.makedirs(os.path.dirname(CHAT_DATA_FILE), exist_ok=True)
    
    states_to_save = {
        'chat_data': chat_data,
        'user_history': user_history
    }
    
    for state_name, state_data in states_to_save.items():
        filepath = STATE_FILES.get(state_name)
        try:
            # Мы не можем напрямую сериализовать datetime, поэтому нужна конвертация
            # В данном случае, это не требуется, т.к. datetime объекты в chat_data
            # и user_history создаются при работе и не хранятся в сложном виде.
            # Если бы хранились, потребовался бы default=str конвертер.
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Ошибка сохранения файла {filepath}: {e}")

def load_state() -> (dict, dict):
    """Загружает состояние chat_data и user_history из JSON-файлов."""
    logging.info("Загрузка состояния бота...")
    
    loaded_chat_data = {}
    loaded_user_history = {}
    
    if os.path.exists(CHAT_DATA_FILE):
        try:
            with open(CHAT_DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_chat_data = json.load(f)
                # JSON ключи всегда строки, конвертируем обратно в int
                loaded_chat_data = {int(k): v for k, v in loaded_chat_data.items()}
        except (json.JSONDecodeError, TypeError) as e:
            logging.error(f"Ошибка загрузки или парсинга {CHAT_DATA_FILE}: {e}. Будет использовано пустое состояние.")
            loaded_chat_data = {}

    if os.path.exists(USER_HISTORY_FILE):
        try:
            with open(USER_HISTORY_FILE, 'r', encoding='utf-8') as f:
                loaded_user_history = json.load(f)
                loaded_user_history = {int(k): v for k, v in loaded_user_history.items()}
        except (json.JSONDecodeError, TypeError) as e:
            logging.error(f"Ошибка загрузки или парсинга {USER_HISTORY_FILE}: {e}. Будет использовано пустое состояние.")
            loaded_user_history = {}
            
    return loaded_chat_data, loaded_user_history
