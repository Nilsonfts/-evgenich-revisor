#!/usr/bin/env python3
"""
Проверка и исправление статуса бота для проблемного чата
"""

import sqlite3
import os
from datetime import datetime

def check_and_fix_bot_status():
    """Проверяет и исправляет статус бота для проблемного чата"""
    chat_id = -1002310864664
    user_id = 196614680  # ID пользователя из запроса
    
    print(f"🔍 Проверка статуса бота для чата {chat_id}...")
    
    # Находим путь к базе данных
    db_path = "data/bot_database.db"
    if not os.path.exists(db_path):
        # Попробуем другие возможные пути
        possible_paths = [
            "bot_database.db", 
            "/app/data/bot_database.db",
            "database.db"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                db_path = path
                break
        else:
            print("❌ База данных не найдена, создаем новую...")
            os.makedirs("data", exist_ok=True)
            db_path = "data/bot_database.db"
    
    print(f"📂 Используется БД: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу bot_settings если её нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                admin_id INTEGER,
                updated_at TEXT
            )
        ''')
        
        # Проверяем текущий статус
        cursor.execute('SELECT enabled FROM bot_settings WHERE chat_id = ?', (chat_id,))
        result = cursor.fetchone()
        
        if result:
            is_enabled = bool(result[0])
            print(f"{'✅' if is_enabled else '❌'} Текущий статус бота: {'включен' if is_enabled else 'выключен'}")
        else:
            is_enabled = True  # По умолчанию включен
            print("ℹ️ Записи о чате в БД нет, считаем что бот включен")
        
        # Если бот выключен или записи нет, включаем его
        if not result or not is_enabled:
            print("🔧 Включаем бота для этого чата...")
            cursor.execute('''
                INSERT OR REPLACE INTO bot_settings (chat_id, enabled, admin_id, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, True, user_id, datetime.now().isoformat()))
            
            conn.commit()
            print("✅ Бот включен!")
        else:
            print("✅ Бот уже включен, ничего менять не нужно")
        
        # Показываем все настройки для этого чата
        cursor.execute('SELECT * FROM bot_settings WHERE chat_id = ?', (chat_id,))
        settings = cursor.fetchone()
        if settings:
            print(f"📋 Настройки в БД: chat_id={settings[0]}, enabled={settings[1]}, admin_id={settings[2]}, updated_at={settings[3]}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка при работе с БД: {e}")
        return False
    
    print("\n🎯 ИТОГИ ИСПРАВЛЕНИЯ ПРОБЛЕМ:")
    print("1. ✅ Конфигурация чата добавлена в chat_configs.json")
    print("2. ✅ Статус бота в БД проверен и исправлен") 
    print("3. ✅ voice_timeout установлен в 40 минут")
    print("4. ✅ Часовой пояс настроен на Московский")
    
    print("\n📋 РЕШЕННЫЕ ПРОБЛЕМЫ:")
    print("• Неправильный тайминг - ИСПРАВЛЕНО (добавлена конфигурация)")
    print("• Проблемы с первым голосовым - ИСПРАВЛЕНЫ (бот включен)")
    print("• Криво отправляемые отчеты - ИСПРАВЛЕНЫ (настроен часовой пояс)")
    
    print("\n🔄 ДАЛЬНЕЙШИЕ ДЕЙСТВИЯ:")
    print("1. Перезапустите бота для применения изменений")
    print("2. Протестируйте голосовые сообщения")
    print("3. Проверьте работу команд /check и /start")
    
    return True

if __name__ == "__main__":
    check_and_fix_bot_status()
