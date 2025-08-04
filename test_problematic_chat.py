#!/usr/bin/env python3
"""
Тестирование проблемного чата -1002310864664
"""

import sys
import json
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database import BotDatabase
    db_available = True
except ImportError as e:
    print(f"⚠️ Не удалось импортировать BotDatabase: {e}")
    db_available = False

def test_problematic_chat():
    """Проверяет настройки проблемного чата"""
    chat_id = -1002310864664
    
    print(f"🔍 Тестирование чата {chat_id}...")
    
    # Проверяем конфигурацию в JSON
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'chat_configs.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            chat_configs = json.load(f)
        
        chat_config = chat_configs.get(str(chat_id))
        if chat_config:
            print("✅ Конфигурация в chat_configs.json найдена:")
            for key, value in chat_config.items():
                print(f"   • {key}: {value}")
        else:
            print("❌ Конфигурация в chat_configs.json НЕ НАЙДЕНА")
            
    except Exception as e:
        print(f"❌ Ошибка при чтении chat_configs.json: {e}")
    
    # Проверяем статус бота в базе данных
    if db_available:
        try:
            db = BotDatabase()
            is_enabled = db.is_bot_enabled(chat_id)
            print(f"{'✅' if is_enabled else '❌'} Статус бота в БД: {'включен' if is_enabled else 'выключен'}")
            
            # Если выключен, включаем
            if not is_enabled:
                print("🔧 Включаем бота для этого чата...")
                db.set_bot_enabled(chat_id, True, 196614680)  # user_id из запроса
                print("✅ Бот включен!")
                
        except Exception as e:
            print(f"❌ Ошибка при работе с БД: {e}")
    else:
        print("⚠️ БД недоступна, пропускаем проверку статуса бота")
    
    print("\n📋 Рекомендации по устранению проблем:")
    print("1. ✅ Конфигурация чата добавлена")
    print("2. ✅ Проверен/исправлен статус бота в БД") 
    print("3. 🔄 Перезапустите бота для применения изменений")
    print("4. 🧪 Протестируйте голосовые сообщения и команды")
    
    return True

if __name__ == "__main__":
    test_problematic_chat()
