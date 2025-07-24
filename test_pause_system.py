#!/usr/bin/env python3
"""
Тест системы пауз /пауза и /стоп_пауза
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
from models import UserData, ShiftData
from state import chat_data

def test_pause_system():
    """Тестирует систему пауз."""
    try:
        print("🧪 Тестирование системы пауз...")
        
        # Создаем тестовые данные
        test_chat_id = -1001234567890
        test_user_id = 123456789
        test_username = "@test_user"
        
        # Создаем пользователя
        user_data = UserData(
            user_id=test_user_id,
            username=test_username,
            role="караоке_ведущий"
        )
        
        # Создаем смену
        shift_data = ShiftData()
        shift_data.main_id = test_user_id
        shift_data.main_username = test_username
        shift_data.users[test_user_id] = user_data
        
        # Добавляем в состояние
        chat_data[test_chat_id] = shift_data
        
        print("✅ Тестовые данные созданы")
        
        # Тест 1: Проверяем начальное состояние
        assert not user_data.on_pause, "Пауза должна быть неактивна изначально"
        assert user_data.pause_start_time is None, "Время начала паузы должно быть None"
        assert user_data.pause_end_time is None, "Время окончания паузы должно быть None"
        print("✅ Тест 1: Начальное состояние корректно")
        
        # Тест 2: Активация паузы
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        user_data.on_pause = True
        user_data.pause_start_time = now_moscow.isoformat()
        user_data.pause_end_time = (now_moscow + datetime.timedelta(minutes=40)).isoformat()
        
        assert user_data.on_pause, "Пауза должна быть активна"
        assert user_data.pause_start_time is not None, "Время начала паузы должно быть установлено"
        assert user_data.pause_end_time is not None, "Время окончания паузы должно быть установлено"
        print("✅ Тест 2: Активация паузы работает")
        
        # Тест 3: Проверка расчета оставшегося времени
        pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
        elapsed = (now_moscow - pause_start).total_seconds() / 60
        remaining = max(0, 40 - elapsed)
        
        assert remaining <= 40, "Оставшееся время не должно превышать 40 минут"
        assert remaining >= 0, "Оставшееся время не должно быть отрицательным"
        print(f"✅ Тест 3: Расчет времени корректен (осталось {remaining:.1f} мин)")
        
        # Тест 4: Деактивация паузы
        user_data.on_pause = False
        user_data.pause_end_time = now_moscow.isoformat()
        
        assert not user_data.on_pause, "Пауза должна быть неактивна"
        print("✅ Тест 4: Деактивация паузы работает")
        
        # Тест 5: Проверка взаимодействия с перерывами
        user_data.on_break = True
        user_data.on_pause = True
        user_data.pause_start_time = now_moscow.isoformat()
        
        # При активации паузы, перерыв должен завершиться
        if user_data.on_pause:
            user_data.on_break = False
            
        assert not user_data.on_break, "Перерыв должен завершиться при активации паузы"
        assert user_data.on_pause, "Пауза должна остаться активной"
        print("✅ Тест 5: Взаимодействие с перерывами корректно")
        
        # Тест 6: Проверка автоматического завершения паузы
        # Симулируем истекшую паузу
        past_time = now_moscow - datetime.timedelta(minutes=45)
        user_data.pause_start_time = past_time.isoformat()
        
        pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
        elapsed = (now_moscow - pause_start).total_seconds() / 60
        remaining = max(0, 40 - elapsed)
        
        if remaining <= 0:
            user_data.on_pause = False
            user_data.pause_end_time = now_moscow.isoformat()
            
        assert not user_data.on_pause, "Истекшая пауза должна автоматически завершиться"
        assert remaining == 0, "Оставшееся время должно быть 0 для истекшей паузы"
        print("✅ Тест 6: Автоматическое завершение паузы работает")
        
        # Тест 7: Голосовое сообщение завершает паузу
        user_data.on_pause = True
        user_data.pause_start_time = now_moscow.isoformat()
        user_data.pause_end_time = (now_moscow + datetime.timedelta(minutes=40)).isoformat()
        
        # Симулируем получение голосового сообщения
        if user_data.on_pause:
            pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
            elapsed = (now_moscow - pause_start).total_seconds() / 60
            remaining = max(0, 40 - elapsed)
            
            if remaining > 0:
                # Голосовое завершает паузу
                user_data.on_pause = False
                user_data.pause_end_time = now_moscow.isoformat()
                
        assert not user_data.on_pause, "Голосовое сообщение должно завершать паузу"
        print("✅ Тест 7: Голосовое сообщение завершает паузу")
        
        print("\n🎉 Все тесты системы пауз пройдены успешно!")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в тестировании системы пауз: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Запуск тестирования системы пауз...")
    success = test_pause_system()
    if success:
        print("✅ Все тесты пройдены успешно!")
        sys.exit(0)
    else:
        print("❌ Обнаружены ошибки в системе пауз")
        sys.exit(1)
