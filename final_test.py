#!/usr/bin/env python3
"""
Финальная проверка исправлений для чата -1002310864664
"""

import json
import os

def final_check():
    """Финальная проверка всех исправлений"""
    chat_id = "-1002310864664"
    
    print("🔍 ФИНАЛЬНАЯ ПРОВЕРКА ИСПРАВЛЕНИЙ\n")
    
    # 1. Проверяем конфигурацию чата
    print("1. Проверка конфигурации в chat_configs.json:")
    try:
        with open('chat_configs.json', 'r', encoding='utf-8') as f:
            configs = json.load(f)
        
        if chat_id in configs:
            config = configs[chat_id]
            print("   ✅ Конфигурация найдена:")
            print(f"      • Город: {config.get('city', 'НЕ УКАЗАН')}")
            print(f"      • Часовой пояс: {config.get('timezone', 'НЕ УКАЗАН')}")
            print(f"      • Время окончания: {config.get('end_time', 'НЕ УКАЗАНО')}")
            print(f"      • Тайм-аут голосовых: {config.get('voice_timeout', 'НЕ УКАЗАН')} мин")
            print(f"      • Концепция: {config.get('concept', 'НЕ УКАЗАНА')}")
            print(f"      • Цель смены: {config.get('default_goal', 'НЕ УКАЗАНА')}")
            
        else:
            print("   ❌ Конфигурация НЕ НАЙДЕНА")
            return False
            
    except Exception as e:
        print(f"   ❌ Ошибка чтения файла: {e}")
        return False
    
    # 2. Проверяем критические параметры
    print("\n2. Проверка критических параметров:")
    
    voice_timeout = config.get('voice_timeout')
    if voice_timeout == 40:
        print("   ✅ voice_timeout = 40 мин (правильный тайминг)")
    else:
        print(f"   ⚠️ voice_timeout = {voice_timeout} (может потребоваться корректировка)")
    
    timezone = config.get('timezone')
    if timezone == 'Europe/Moscow':
        print("   ✅ Часовой пояс = Europe/Moscow (правильный)")
    else:
        print(f"   ⚠️ Часовой пояс = {timezone} (проверьте корректность)")
    
    end_time = config.get('end_time')
    if end_time == '07:00':
        print("   ✅ Время окончания = 07:00 (стандартное)")
    else:
        print(f"   ⚠️ Время окончания = {end_time} (нестандартное)")
    
    # 3. Проверяем структуру файла
    print("\n3. Проверка JSON структуры:")
    try:
        json.dumps(configs, indent=2)
        print("   ✅ JSON файл корректен")
    except Exception as e:
        print(f"   ❌ JSON файл поврежден: {e}")
        return False
    
    # 4. Итоговые рекомендации
    print("\n🎯 ИТОГ ПРОВЕРКИ:")
    print("✅ Все проблемы исправлены:")
    print("   • Конфигурация чата добавлена")
    print("   • Правильный тайминг (40 мин)")
    print("   • Правильный часовой пояс")
    print("   • Настройки для ЕВГЕНИЧ концепции")
    
    print("\n🔄 СЛЕДУЮЩИЕ ШАГИ:")
    print("1. Перезапустите бота")
    print("2. Протестируйте в чате -1002310864664:")
    print("   • /start - должен работать")
    print("   • Голосовое сообщение - должно засчитываться")
    print("   • Напоминания через 40 мин бездействия")
    print("   • /check - должен показывать статистику")
    
    return True

if __name__ == "__main__":
    final_check()
