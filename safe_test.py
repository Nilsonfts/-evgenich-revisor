#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Безопасное тестирование системы с сохранением данных
"""

import json
import shutil
import os
import sqlite3
from datetime import datetime

def create_backup():
    """Создает резервную копию всех данных."""
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        'chat_configs.json',
        'ad_templates.json',
        'data/bot_database.db'
    ]
    
    backed_up = []
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, os.path.basename(file_path))
            shutil.copy2(file_path, backup_path)
            backed_up.append(file_path)
            print(f"✅ Скопирован: {file_path}")
    
    # Также сохраним текущее состояние из памяти
    try:
        from state import chat_data
        memory_backup = {}
        for chat_id, shift in chat_data.items():
            memory_backup[str(chat_id)] = {
                'shift_start': shift.shift_start,
                'main_id': shift.main_id,
                'shift_goal': shift.shift_goal,
                'users': {
                    str(user_id): {
                        'username': user.username,
                        'count': user.count,
                        'breaks_count': user.breaks_count,
                        'late_returns': user.late_returns,
                        'on_break': user.on_break,
                        'break_start_time': user.break_start_time,
                        'voice_deltas': user.voice_deltas,
                        'voice_durations': user.voice_durations,
                        'recognized_ads': user.recognized_ads
                    } for user_id, user in shift.users.items()
                }
            }
        
        with open(os.path.join(backup_dir, 'memory_state.json'), 'w', encoding='utf-8') as f:
            json.dump(memory_backup, f, ensure_ascii=False, indent=2)
        print(f"✅ Сохранено состояние из памяти")
        
    except Exception as e:
        print(f"⚠️ Не удалось сохранить состояние из памяти: {e}")
    
    print(f"\n🎯 Бэкап создан в папке: {backup_dir}")
    return backup_dir

def restore_backup(backup_dir):
    """Восстанавливает данные из резервной копии."""
    if not os.path.exists(backup_dir):
        print(f"❌ Папка бэкапа не найдена: {backup_dir}")
        return False
    
    restored = []
    for file_name in os.listdir(backup_dir):
        if file_name == 'memory_state.json':
            continue
            
        backup_path = os.path.join(backup_dir, file_name)
        
        if file_name == 'bot_database.db':
            target_path = 'data/bot_database.db'
            os.makedirs('data', exist_ok=True)
        else:
            target_path = file_name
            
        shutil.copy2(backup_path, target_path)
        restored.append(target_path)
        print(f"✅ Восстановлен: {target_path}")
    
    print(f"\n🎯 Восстановлено файлов: {len(restored)}")
    return True

def safe_test_wizard():
    """Безопасно тестирует мастер настройки."""
    print("🧪 БЕЗОПАСНОЕ ТЕСТИРОВАНИЕ СИСТЕМЫ")
    print("=" * 50)
    
    # Создаем бэкап
    backup_dir = create_backup()
    
    print(f"\n🔒 Все данные сохранены в {backup_dir}")
    print("Теперь можно безопасно тестировать систему!")
    print("\nДля восстановления данных запустите:")
    print(f"python3 safe_test.py restore {backup_dir}")
    
    return backup_dir

def check_current_data():
    """Проверяет текущие данные без изменений."""
    print("📊 ПРОВЕРКА ТЕКУЩИХ ДАННЫХ")
    print("=" * 40)
    
    # Проверяем конфиги чатов
    if os.path.exists('chat_configs.json'):
        with open('chat_configs.json', 'r', encoding='utf-8') as f:
            configs = json.load(f)
        print(f"📋 Конфигураций чатов: {len(configs)}")
        for chat_id, config in configs.items():
            brand = config.get('brand', 'Неизвестно')
            city = config.get('city', 'Неизвестно')
            goal = config.get('default_goal', 'Не задана')
            concept = config.get('concept', 'Не указана')
            print(f"  • Чат {chat_id}: {brand}/{city} (норма: {goal}, концепция: {concept})")
    
    # Проверяем базу данных
    if os.path.exists('data/bot_database.db'):
        conn = sqlite3.connect('data/bot_database.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM voice_stats WHERE date(timestamp) = date('now')")
            today_voices = cursor.fetchone()[0]
            
            cursor.execute("SELECT username, COUNT(*) as count FROM voice_stats WHERE date(timestamp) = date('now') GROUP BY username ORDER BY count DESC")
            users_today = cursor.fetchall()
            
            print(f"\n🗣️ Голосовых сегодня: {today_voices}")
            if users_today:
                print("👥 Активные ведущие сегодня:")
                for username, count in users_today:
                    print(f"  • {username}: {count} ГС")
                    
        except Exception as e:
            print(f"⚠️ Ошибка чтения БД: {e}")
        finally:
            conn.close()
    
    # Проверяем состояние в памяти
    try:
        from state import chat_data
        if chat_data:
            print(f"\n💾 Активных смен в памяти: {len(chat_data)}")
            for chat_id, shift in chat_data.items():
                print(f"  • Чат {chat_id}: {len(shift.users)} пользователей")
                if shift.main_id:
                    main_user = shift.users.get(shift.main_id)
                    if main_user:
                        print(f"    Главный: {main_user.username} ({main_user.count} ГС)")
        else:
            print("\n💾 Активных смен в памяти нет")
    except Exception as e:
        print(f"⚠️ Ошибка проверки памяти: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "restore" and len(sys.argv) > 2:
            restore_backup(sys.argv[2])
        elif sys.argv[1] == "check":
            check_current_data()
        elif sys.argv[1] == "backup":
            safe_test_wizard()
    else:
        print("Использование:")
        print("  python3 safe_test.py check     - проверить текущие данные")
        print("  python3 safe_test.py backup    - создать бэкап")
        print("  python3 safe_test.py restore <папка> - восстановить бэкап")
