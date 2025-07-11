# state_manager.py
import json
import logging
import os
import shutil
import copy
from dataclasses import asdict

from state import data_lock
from database import db  # Импортируем базу данных

CHAT_DATA_FILE = 'data/chat_data.json'
USER_HISTORY_FILE = 'data/user_history.json'

# ДОБАВЛЕНО: Класс-кодировщик для правильного сохранения dataclasses в JSON
class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, '__dataclass_fields__'):
            return asdict(o)
        return super().default(o)

def save_state(bot, chat_data: dict, user_history: dict):
    """
    Потокобезопасно сохраняет текущее состояние в JSON-файлы и базу данных.
    """
    logging.info("Начинаю сохранение состояния бота...")
    
    os.makedirs(os.path.dirname(CHAT_DATA_FILE), exist_ok=True)
    
    with data_lock:
        chat_data_copy = copy.deepcopy(chat_data)
        user_history_copy = copy.deepcopy(user_history)
    
    # Сохраняем в базу данных
    try:
        for chat_id, shift_data in chat_data_copy.items():
            if shift_data and hasattr(shift_data, 'main_id'):
                db.save_shift_data(chat_id, shift_data)
        logging.info("Состояние успешно сохранено в базу данных")
    except Exception as e:
        logging.error(f"Ошибка сохранения в базу данных: {e}")
    
    # Сохраняем в JSON файлы (для совместимости)
    states_to_save = {
        'chat_data': (chat_data_copy, CHAT_DATA_FILE),
        'user_history': (user_history_copy, USER_HISTORY_FILE)
    }
    
    for state_name, (data_to_save, filepath) in states_to_save.items():
        backup_filepath = filepath + ".bak"
        try:
            if os.path.exists(filepath):
                shutil.copyfile(filepath, backup_filepath)

            temp_filepath = filepath + ".tmp"
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                # ИЗМЕНЕНО: Используем наш кастомный кодировщик напрямую здесь
                json.dump(data_to_save, f, indent=4, ensure_ascii=False, cls=EnhancedJSONEncoder)
            
            os.replace(temp_filepath, filepath)

            if os.path.exists(backup_filepath):
                os.remove(backup_filepath)

        except Exception as e:
            logging.error(f"Критическая ошибка при сохранении файла {filepath}: {e}", exc_info=True)
            if os.path.exists(backup_filepath):
                logging.info(f"Восстановление файла {filepath} из бэкапа...")
                try:
                    shutil.move(backup_filepath, filepath)
                except Exception as restore_e:
                    logging.error(f"Не удалось восстановить бэкап для {filepath}: {restore_e}")
                    from config import BOSS_ID
                    if BOSS_ID:
                        try:
                            bot.send_message(BOSS_ID, f"🚨 **Критическая ошибка!**\nНе удалось сохранить и восстановить состояние `{state_name}`. Проверьте логи и дисковое пространство!")
                        except Exception as send_e:
                            logging.error(f"Не удалось отправить уведомление BOSS_ID: {send_e}")

def load_state() -> tuple[dict, dict]:
    """
    Загружает состояние из JSON-файлов, с попыткой восстановления из бэкапа.
    """
    logging.info("Загрузка состояния бота...")
    
    def _load_single_file(filepath):
        backup_filepath = filepath + ".bak"
        if not os.path.exists(filepath) and os.path.exists(backup_filepath):
            logging.warning(f"Основной файл {filepath} не найден, восстанавливаем из бэкапа.")
            shutil.copyfile(backup_filepath, filepath)

        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    # Проверяем, не пустой ли файл
                    content = f.read()
                    if not content:
                        logging.warning(f"Файл состояния {filepath} пустой.")
                        return {}
                    data = json.loads(content)
                    return {int(k): v for k, v in data.items()}
            except (json.JSONDecodeError, TypeError) as e:
                logging.error(f"Ошибка парсинга {filepath}: {e}. Попробуйте проверить файл вручную.")
                return {}
        return {}

    loaded_chat_data = _load_single_file(CHAT_DATA_FILE)
    loaded_user_history = _load_single_file(USER_HISTORY_FILE)
            
    return loaded_chat_data, loaded_user_history
