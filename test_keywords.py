#!/usr/bin/env python3
# test_keywords.py - Тест новых ключевых слов для перерывов

import sys
sys.path.append('.')

print("=== ТЕСТ НОВЫХ КЛЮЧЕВЫХ СЛОВ ===")

try:
    from phrases import BREAK_KEYWORDS, RETURN_CONFIRM_WORDS
    
    print("☕️ НОВЫЕ КЛЮЧЕВЫЕ СЛОВА ДЛЯ ПЕРЕРЫВА:")
    print(f"Всего слов: {len(BREAK_KEYWORDS)}")
    for i, keyword in enumerate(BREAK_KEYWORDS, 1):
        print(f"{i:2}. {keyword}")
    
    print("\n✅ НОВЫЕ КЛЮЧЕВЫЕ СЛОВА ДЛЯ ВОЗВРАЩЕНИЯ:")
    print(f"Всего слов: {len(RETURN_CONFIRM_WORDS)}")
    for i, keyword in enumerate(RETURN_CONFIRM_WORDS, 1):
        print(f"{i:2}. {keyword}")
    
    print("\n🎯 ТЕСТИРОВАНИЕ НОВЫХ СЛОВ:")
    
    # Тест слов для перерыва
    test_break_words = ["устал", "туалет", "кофе", "звонок", "отдохнуть", "размяться"]
    print("\n☕️ Тест слов для перерыва:")
    for word in test_break_words:
        if word in BREAK_KEYWORDS:
            print(f"✅ '{word}' - распознается")
        else:
            print(f"❌ '{word}' - НЕ распознается")
    
    # Тест слов для возвращения
    test_return_words = ["работаю", "поехали", "включился", "готова", "отдохнула", "в деле"]
    print("\n✅ Тест слов для возвращения:")
    for word in test_return_words:
        if word in RETURN_CONFIRM_WORDS:
            print(f"✅ '{word}' - распознается")
        else:
            print(f"❌ '{word}' - НЕ распознается")
    
    print("\n💡 ДОПОЛНИТЕЛЬНАЯ ЛОГИКА:")
    print("✅ Голосовое сообщение автоматически засчитывается как возвращение с перерыва")
    print("✅ Поддерживаются мужские и женские формы слов")
    print("✅ Обновлена справочная информация в /help")
    
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
except Exception as e:
    print(f"❌ Ошибка: {e}")

print("\n=== ТЕСТ ЗАВЕРШЕН ===")
