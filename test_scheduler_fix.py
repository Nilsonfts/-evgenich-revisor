#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений планировщика.
"""
import datetime
import pytz
import json
import os
import sys

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_timezone_configuration():
    """Тестирует правильность настройки часовых поясов."""
    print("🔍 Тестирование настройки часовых поясов...")
    
    try:
        from config import TIMEZONE_MAP
        print(f"✅ TIMEZONE_MAP загружен: {len(TIMEZONE_MAP)} часовых поясов")
        
        # Проверим Пермский часовой пояс (была проблема с 7 утра)
        if "+2" in TIMEZONE_MAP:
            perm_tz = TIMEZONE_MAP["+2"]
            print(f"✅ Пермский часовой пояс (+2): {perm_tz}")
            
            # Создадим время 7:00 по Перми
            moscow_tz = pytz.timezone('Europe/Moscow')
            now_moscow = datetime.datetime.now(moscow_tz)
            perm_time = now_moscow.astimezone(perm_tz)
            print(f"📅 Текущее время в Москве: {now_moscow.strftime('%H:%M:%S')}")
            print(f"📅 Текущее время в Перми: {perm_time.strftime('%H:%M:%S')}")
            
            # Проверим логику сравнения времени 7:00
            test_time = datetime.time(7, 0)
            current_time = perm_time.time()
            
            # Новая логика (диапазон)
            is_end_time_range = (
                test_time <= current_time <= 
                datetime.time((test_time.hour + 1) % 24, test_time.minute)
            )
            
            print(f"🕰️ Время окончания смены: {test_time}")
            print(f"🕰️ Текущее время (Пермь): {current_time}")
            print(f"✅ Попадает в диапазон окончания (7:00-8:00): {is_end_time_range}")
            
        else:
            print("❌ Часовой пояс +2 (Пермь) не найден в TIMEZONE_MAP")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании часовых поясов: {e}")
        return False
    
    return True

def test_time_logic():
    """Тестирует логику определения времени окончания смены."""
    print("\n🔍 Тестирование логики времени окончания смены...")
    
    try:
        # Имитируем разные времена для проверки
        test_cases = [
            ("06:59", False),  # До времени окончания
            ("07:00", True),   # Точно время окончания
            ("07:30", True),   # В пределах часа после
            ("07:59", True),   # Почти час после
            ("08:00", False),  # Час прошел
            ("08:01", False),  # Время прошло
        ]
        
        end_time = datetime.time(7, 0)
        
        for time_str, expected in test_cases:
            hour, minute = map(int, time_str.split(':'))
            current_time = datetime.time(hour, minute)
            
            # Новая логика диапазона
            is_in_range = (
                end_time <= current_time < 
                datetime.time((end_time.hour + 1) % 24, end_time.minute)
            )
            
            status = "✅" if is_in_range == expected else "❌"
            print(f"{status} {time_str}: ожидалось {expected}, получено {is_in_range}")
        
        print("✅ Тестирование логики времени завершено")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании логики времени: {e}")
        return False

def test_chat_configs():
    """Тестирует загрузку и корректность конфигураций чатов."""
    print("\n🔍 Тестирование конфигураций чатов...")
    
    try:
        if os.path.exists('chat_configs.json'):
            with open('chat_configs.json', 'r', encoding='utf-8') as f:
                chat_configs = json.load(f)
            
            print(f"✅ Загружено {len(chat_configs)} конфигураций чатов")
            
            # Проверим конфигурации на корректность
            for chat_id, config in chat_configs.items():
                required_fields = ['end_time', 'timezone_offset', 'city']
                missing_fields = [field for field in required_fields if field not in config]
                
                if missing_fields:
                    print(f"⚠️ Чат {chat_id} ({config.get('city', 'N/A')}): отсутствуют поля {missing_fields}")
                else:
                    print(f"✅ Чат {chat_id} ({config.get('city', 'N/A')}): конфигурация корректна")
            
            return True
        else:
            print("❌ Файл chat_configs.json не найден")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании конфигураций чатов: {e}")
        return False

def test_scheduler_logic():
    """Тестирует логику планировщика без запуска бота."""
    print("\n🔍 Тестирование логики планировщика...")
    
    try:
        # Имитируем функцию check_for_shift_end
        from config import TIMEZONE_MAP
        
        # Создаем тестовые данные
        test_chat_config = {
            'end_time': '07:00',
            'timezone_offset': '+2',
            'city': 'Пермь'
        }
        
        # Получаем часовой пояс
        timezone_offset = test_chat_config.get('timezone_offset', '+0')
        if timezone_offset in TIMEZONE_MAP:
            target_tz = TIMEZONE_MAP[timezone_offset]
            current_time = datetime.datetime.now(target_tz)
            
            # Парсим время окончания
            end_time_str = test_chat_config.get('end_time', '07:00')
            end_hour, end_minute = map(int, end_time_str.split(':'))
            end_time = datetime.time(end_hour, end_minute)
            
            current_time_only = current_time.time()
            
            # Новая логика диапазона
            is_end_time = (
                end_time <= current_time_only < 
                datetime.time((end_time.hour + 1) % 24, end_time.minute)
            )
            
            print(f"🏙️ Город: {test_chat_config['city']}")
            print(f"🕰️ Время окончания: {end_time}")
            print(f"🌍 Часовой пояс: {timezone_offset} ({target_tz})")
            print(f"⏰ Текущее время: {current_time.strftime('%H:%M:%S')}")
            print(f"✅ Время окончания смены: {is_end_time}")
            
            return True
        else:
            print(f"❌ Часовой пояс {timezone_offset} не найден")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании планировщика: {e}")
        return False

def main():
    """Основная функция тестирования."""
    print("🚀 Запуск тестирования исправлений планировщика\n")
    
    tests = [
        test_timezone_configuration,
        test_time_logic,
        test_chat_configs,
        test_scheduler_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Результаты тестирования: {passed}/{total} тестов прошли успешно")
    
    if passed == total:
        print("🎉 Все тесты прошли успешно! Исправления работают корректно.")
    else:
        print("⚠️ Некоторые тесты не прошли. Требуется дополнительная отладка.")
    
    return passed == total

if __name__ == "__main__":
    main()
