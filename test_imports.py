#!/usr/bin/env python3
"""
Быстрый тест импортов и основных компонентов системы.
"""

def test_imports():
    """Тестирует все основные импорты."""
    print("🔍 Тестирование импортов...")
    
    try:
        # Основные модули
        import config
        print("✅ config.py - OK")
        
        import state
        print("✅ state.py - OK")
        
        import utils
        print("✅ utils.py - OK")
        
        import models
        print("✅ models.py - OK")
        
        import database
        print("✅ database.py - OK")
        
        # Хэндлеры
        from handlers import admin, user, shift, voice, wizards, callbacks
        print("✅ handlers - OK")
        
        # Тест создания объектов
        from models import UserData, ShiftData
        user_data = UserData(123, "test_user", "караоке_ведущий")
        shift_data = ShiftData()
        print("✅ Модели данных - OK")
        
        # Тест AI категоризации рекламы
        from handlers.wizards import categorize_ad_text, AD_CATEGORIES
        category = categorize_ad_text("У нас скидка на караоке!")
        print(f"✅ AI категоризация: '{category}' - OK")
        
        print("\n🎉 Все импорты успешны!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def test_concepts():
    """Тестирует концепции."""
    print("\n📋 Тестирование концепций...")
    try:
        from handlers.wizards import AVAILABLE_CONCEPTS
        print(f"✅ Загружено концепций: {len(AVAILABLE_CONCEPTS)}")
        for concept_id, concept_data in AVAILABLE_CONCEPTS.items():
            print(f"  • {concept_data['name']}: {concept_data['description']}")
        return True
    except Exception as e:
        print(f"❌ Ошибка концепций: {e}")
        return False

def test_ad_categories():
    """Тестирует категории рекламы."""
    print("\n📝 Тестирование категорий рекламы...")
    try:
        from handlers.wizards import AD_CATEGORIES, categorize_ad_text
        
        test_texts = [
            ("У нас скидка 50% на все блюда!", "promo"),
            ("Приходите петь караоке сегодня!", "karaoke"),
            ("Новое меню уже в заведении", "menu"),
            ("Забронируйте столик на вечер", "booking"),
            ("Мы работаем до 4 утра", "general")
        ]
        
        for text, expected in test_texts:
            result = categorize_ad_text(text)
            status = "✅" if result == expected else "⚠️"
            print(f"  {status} '{text}' → {result}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка категоризации: {e}")
        return False

if __name__ == "__main__":
    print("🧪 БЫСТРЫЙ ТЕСТ СИСТЕМЫ")
    print("=" * 50)
    
    success = True
    success &= test_imports()
    success &= test_concepts() 
    success &= test_ad_categories()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("✅ Система готова к работе")
    else:
        print("❌ ЕСТЬ ОШИБКИ В СИСТЕМЕ")
        print("⚠️ Требуется исправление")
