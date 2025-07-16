#!/usr/bin/env python3
"""
Простой тест системы отчетов
"""

import sys
import os
import logging
import datetime
import pytz

# Добавляем текущую директорию в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Импортируем необходимые модули
from models import ShiftData, UserData
from utils import generate_detailed_report
import state

def test_simple_report():
    """Простой тест генерации отчета."""
    print("🔍 Простой тест системы отчетов...")
    
    # Создаем тестовые данные
    test_chat_id = -1001234567890
    test_user_id = 123456789
    test_username = "Евгенич_Тест"
    
    # Создаем объект данных смены
    shift_data = ShiftData(
        main_id=test_user_id,
        shift_goal=15,
        shift_start_time=datetime.datetime.now(pytz.timezone('Europe/Moscow')).isoformat(),
        timezone="0"
    )
    
    # Создаем тестовые данные пользователя
    user_data = UserData(user_id=test_user_id, username=test_username)
    user_data.count = 12  # 12 голосовых
    user_data.breaks_count = 2  # 2 перерыва 
    user_data.late_returns = 1  # 1 опоздание
    user_data.voice_deltas = [3.5, 4.2, 2.8, 5.1, 3.9]  # Интервалы между ГС
    user_data.voice_durations = [25.5, 30.2, 18.7, 22.3, 28.1]  # Длительность ГС
    user_data.recognized_ads = ["Меню", "Акция на напитки", "Меню", "Караоке-час"]  # Темы
    
    shift_data.users[test_user_id] = user_data
    
    print(f"✅ Создан тестовый объект смены:")
    print(f"   🎤 Ведущий: {user_data.username}")
    print(f"   📊 Голосовых: {user_data.count}/{shift_data.shift_goal} ({user_data.count/shift_data.shift_goal*100:.0f}%)")
    print(f"   ☕ Перерывов: {user_data.breaks_count}")
    print(f"   ⏰ Опозданий: {user_data.late_returns}")
    print(f"   🎯 Средний ритм: {sum(user_data.voice_deltas)/len(user_data.voice_deltas):.1f} мин/ГС")
    print(f"   📝 Распознано тем: {len(user_data.recognized_ads)}")
    
    # Тестируем генерацию отчета
    print("\n📋 Тестирование генерации отчета...")
    try:
        report_lines = generate_detailed_report(test_chat_id, shift_data)
        if report_lines:
            print("✅ Отчет успешно сгенерирован:")
            print("=" * 60)
            for line in report_lines:
                print(line)
            print("=" * 60)
            
            # Проверяем основные элементы отчета
            report_text = "\n".join(report_lines)
            checks = [
                ("Заголовок отчета", "#ОтчетВедущего" in report_text),
                ("Имя ведущего", test_username in report_text),
                ("Количество голосовых", f"{user_data.count}" in report_text),
                ("План смены", f"{shift_data.shift_goal}" in report_text),
                ("Процент выполнения", "80%" in report_text),
                ("Количество перерывов", f"{user_data.breaks_count}" in report_text),
                ("Опоздания", f"{user_data.late_returns}" in report_text),
                ("Средний ритм", "3.9" in report_text),
                ("Анализ контента", "Меню (x2)" in report_text)
            ]
            
            print("\n🔍 Проверка элементов отчета:")
            all_passed = True
            for check_name, result in checks:
                status = "✅" if result else "❌"
                print(f"   {status} {check_name}: {'OK' if result else 'FAIL'}")
                if not result:
                    all_passed = False
            
            if all_passed:
                print("\n🎉 Все проверки пройдены успешно!")
                return True
            else:
                print("\n⚠️ Некоторые проверки не пройдены")
                return False
                
        else:
            print("❌ Отчет пустой")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка генерации отчета: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_google_sheets_integration():
    """Тест интеграции с Google Sheets."""
    print("\n📊 Тестирование интеграции с Google Sheets...")
    
    try:
        from config import GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON
        from g_sheets import get_sheet, append_shift_to_google_sheet
        
        if not GOOGLE_SHEET_KEY or not GOOGLE_CREDENTIALS_JSON:
            print("ℹ️ Google Sheets не настроен - пропускаем тест")
            return True
        
        print("✅ Переменные Google Sheets найдены")
        
        # Проверяем подключение
        sheet = get_sheet()
        if sheet:
            print("✅ Подключение к Google Sheets успешно")
            
            # Создаем тестовые данные
            test_chat_id = -1001234567890
            test_user_id = 123456789
            
            shift_data = ShiftData(
                main_id=test_user_id,
                shift_goal=15,
                shift_start_time=datetime.datetime.now().isoformat(),
                timezone="0"
            )
            
            user_data = UserData(user_id=test_user_id, username="Тест_Ведущий")
            user_data.count = 10
            user_data.breaks_count = 1
            user_data.late_returns = 0
            user_data.voice_deltas = [4.0, 3.5, 4.2]
            user_data.voice_durations = [25.0, 28.0, 22.0]
            user_data.recognized_ads = ["Тест", "Меню"]
            
            shift_data.users[test_user_id] = user_data
            
            # Мок-бот для тестирования
            class MockBot:
                def get_chat(self, chat_id):
                    class MockChat:
                        title = f"Тестовый чат {chat_id}"
                    return MockChat()
            
            # Тестируем выгрузку
            analytical_conclusion = "Тестовая рекомендация для проверки системы"
            append_shift_to_google_sheet(MockBot(), test_chat_id, shift_data, analytical_conclusion)
            print("✅ Тестовая выгрузка в Google Sheets выполнена")
            
        else:
            print("⚠️ Не удалось подключиться к Google Sheets")
            return False
            
    except ImportError as e:
        print(f"ℹ️ Модуль gspread не найден: {e}")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка тестирования Google Sheets: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Запуск простого тестирования системы отчетов...")
    
    # Основной тест генерации отчетов
    success1 = test_simple_report()
    
    # Тест Google Sheets (опционально)
    success2 = test_google_sheets_integration()
    
    if success1 and success2:
        print("\n✅ Все тесты пройдены успешно!")
        print("💡 Система отчетов работает корректно")
        sys.exit(0)
    else:
        print("\n❌ Обнаружены проблемы в системе отчетов")
        sys.exit(1)
