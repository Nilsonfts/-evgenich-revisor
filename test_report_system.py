#!/usr/bin/env python3
"""
Тест системы отчетов
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
from database import db
from models import ShiftData, UserData
from utils import generate_detailed_report
from g_sheets import append_shift_to_google_sheet
from config import TIMEZONE_MAP
import state

def test_report_generation():
    """Тестирует генерацию отчетов."""
    print("🔍 Тестирование системы отчетов...")
    
    # Инициализируем базу данных
    init_database()
    print("✅ База данных инициализирована")
    
    # Создаем тестовую смену
    test_chat_id = -1001234567890
    test_user_id = 123456789
    test_username = "test_host"
    
    # Проверяем есть ли уже активная смена
    existing_shift = get_shift_by_chat_id(test_chat_id)
    if existing_shift:
        print(f"ℹ️ Найдена активная смена в чате {test_chat_id}")
    else:
        # Создаем новую смену
        success = create_shift(
            chat_id=test_chat_id,
            main_id=test_user_id,
            main_username=test_username,
            shift_goal=15,
            timezone="0"  # Москва
        )
        if success:
            print(f"✅ Создана тестовая смена в чате {test_chat_id}")
        else:
            print("❌ Ошибка создания смены")
            return False
    
    # Создаем данные пользователя
    user_success = create_user_shift_data(
        chat_id=test_chat_id,
        user_id=test_user_id,
        username=test_username,
        role="караоке_ведущий"
    )
    print(f"{'✅' if user_success else '❌'} Данные пользователя: {user_success}")
    
    # Создаем объект данных смены для тестирования
    shift_data = ShiftData(
        main_id=test_user_id,
        shift_goal=15,
        shift_start=datetime.datetime.now(pytz.timezone('Europe/Moscow')).isoformat(),
        timezone="0"
    )
    
    # Создаем тестовые данные пользователя
    user_data = UserData(username=test_username)
    user_data.count = 12  # 12 голосовых
    user_data.breaks_count = 2  # 2 перерыва
    user_data.late_returns = 1  # 1 опоздание
    user_data.voice_deltas = [3.5, 4.2, 2.8, 5.1, 3.9]  # Интервалы между ГС
    user_data.voice_durations = [25.5, 30.2, 18.7, 22.3, 28.1]  # Длительность ГС
    user_data.recognized_ads = ["Меню", "Акция", "Меню", "Караоке"]  # Темы
    
    shift_data.users[test_user_id] = user_data
    
    # Добавляем в состояние
    state.chat_data[test_chat_id] = shift_data
    
    print(f"✅ Создан тестовый объект смены:")
    print(f"   🎤 Ведущий: {user_data.username}")
    print(f"   📊 Голосовых: {user_data.count}/{shift_data.shift_goal}")
    print(f"   ☕ Перерывов: {user_data.breaks_count}")
    print(f"   ⏰ Опозданий: {user_data.late_returns}")
    
    # Тестируем генерацию отчета
    print("\n📋 Тестирование генерации отчета...")
    try:
        report_lines = generate_detailed_report(test_chat_id, shift_data)
        if report_lines:
            print("✅ Отчет успешно сгенерирован:")
            print("=" * 50)
            for line in report_lines:
                print(line)
            print("=" * 50)
        else:
            print("❌ Отчет пустой")
            return False
    except Exception as e:
        print(f"❌ Ошибка генерации отчета: {e}")
        return False
    
    # Тестируем выгрузку в Google Sheets (если настроено)
    print("\n📊 Тестирование выгрузки в Google Sheets...")
    try:
        # Импортируем переменные конфигурации
        from config import GOOGLE_SHEET_KEY, GOOGLE_CREDENTIALS_JSON
        
        if GOOGLE_SHEET_KEY and GOOGLE_CREDENTIALS_JSON:
            print("ℹ️ Google Sheets настроен, пробуем выгрузку...")
            # Создаем мок-бота для тестирования
            class MockBot:
                def get_chat(self, chat_id):
                    class MockChat:
                        title = f"Тестовый чат {chat_id}"
                    return MockChat()
            
            mock_bot = MockBot()
            analytical_conclusion = "Тестовая рекомендация: показатели в норме"
            
            append_shift_to_google_sheet(mock_bot, test_chat_id, shift_data, analytical_conclusion)
            print("✅ Выгрузка в Google Sheets выполнена")
        else:
            print("ℹ️ Google Sheets не настроен (это нормально для тестирования)")
    except Exception as e:
        print(f"⚠️ Ошибка выгрузки в Google Sheets: {e}")
        print("   (Это не критично если Google Sheets не настроен)")
    
    print("\n🎉 Тест системы отчетов завершен!")
    return True

if __name__ == "__main__":
    print("🚀 Запуск тестирования системы отчетов...")
    success = test_report_generation()
    if success:
        print("✅ Все тесты пройдены успешно!")
        sys.exit(0)
    else:
        print("❌ Обнаружены ошибки в системе отчетов")
        sys.exit(1)
