# state_manager.py
import json
import logging
import os
import shutil # Библиотека для операций с файлами

# Пути к файлам, где будут храниться данные.
CHAT_DATA_FILE = 'data/chat_data.json'
USER_HISTORY_FILE = 'data/user_history.json'

def save_state(chat_data: dict, user_history: dict):
    """
    Сохраняет текущее состояние chat_data и user_history в JSON-файлы.
    ИЗМЕНЕНО: Добавлено резервное копирование перед сохранением.
    """
    logging.info("Начинаю сохранение состояния бота...")
    
    os.makedirs(os.path.dirname(CHAT_DATA_FILE), exist_ok=True)
    
    states_to_save = {
        'chat_data': (chat_data, CHAT_DATA_FILE),
        'user_history': (user_history, USER_HISTORY_FILE)
    }
    
    for state_name, (data_to_save, filepath) in states_to_save.items():
        backup_filepath = filepath + ".bak"
        try:
            # 1. Если основной файл существует, создаем бэкап
            if os.path.exists(filepath):
                shutil.copyfile(filepath, backup_filepath)

            # 2. Пишем данные во временный файл
            temp_filepath = filepath + ".tmp"
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                # Используем default=str для безопасной сериализации объектов, которые могут быть не JSON-совместимы
                json.dump(data_to_save, f, indent=4, ensure_ascii=False, default=str)
            
            # 3. Атомарно переименовываем временный файл в основной
            os.replace(temp_filepath, filepath)

            # 4. Если все прошло успешно, удаляем бэкап
            if os.path.exists(backup_filepath):
                os.remove(backup_filepath)

        except Exception as e:
            logging.error(f"Критическая ошибка при сохранении файла {filepath}: {e}", exc_info=True)
            # Если произошла ошибка, пытаемся восстановить из бэкапа
            if os.path.exists(backup_filepath):
                logging.info(f"Восстановление файла {filepath} из бэкапа {backup_filepath}...")
                shutil.move(backup_filepath, filepath)

def load_state() -> (dict, dict):
    """
    Загружает состояние chat_data и user_history из JSON-файлов.
    ИЗМЕНЕНО: Более устойчивая загрузка с попыткой восстановления из бэкапа.
    """
    logging.info("Загрузка состояния бота...")
    
    def _load_single_file(filepath):
        """Вспомогательная функция для загрузки одного файла."""
        backup_filepath = filepath + ".bak"
        if not os.path.exists(filepath) and os.path.exists(backup_filepath):
            logging.warning(f"Основной файл состояния {filepath} не найден, но найден бэкап. Восстанавливаем из бэкапа.")
            shutil.copyfile(backup_filepath, filepath)

        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Конвертируем ключи словарей в int, так как chat_id - это число
                    return {int(k): v for k, v in data.items()}
            except (json.JSONDecodeError, TypeError) as e:
                logging.error(f"Ошибка парсинга файла {filepath}: {e}. Попробуйте проверить его вручную.")
                return {}
        return {}

    loaded_chat_data = _load_single_file(CHAT_DATA_FILE)
    loaded_user_history = _load_single_file(USER_HISTORY_FILE)
            
    return loaded_chat_data, loaded_user_history
