#!/usr/bin/env python3
# test_wizard_priority.py - Тест приоритета обработчиков

import sys
sys.path.append('.')

print("=== ТЕСТ ПРИОРИТЕТА ОБРАБОТЧИКОВ ===")

# Проверяем, какие обработчики setup_wizard зарегистрированы
try:
    import telebot
    from config import BOT_TOKEN
    
    # Создаем тестового бота с фиктивным, но правильным токеном
    test_bot = telebot.TeleBot("123456789:AAETestTokenForTestingPurposesOnly", threaded=False)
    
    # Регистрируем обработчики в том же порядке, что и в main.py
    import handlers
    handlers.register_handlers(test_bot)
    
    # Проверяем зарегистрированные обработчики
    message_handlers = test_bot.message_handlers
    setup_wizard_handlers = []
    
    for handler in message_handlers:
        if hasattr(handler, 'commands') and 'setup_wizard' in handler.commands:
            setup_wizard_handlers.append(handler)
    
    print(f"Найдено обработчиков setup_wizard: {len(setup_wizard_handlers)}")
    
    for i, handler in enumerate(setup_wizard_handlers):
        print(f"Обработчик {i+1}: {handler.function.__name__} из {handler.function.__module__}")
        
    if len(setup_wizard_handlers) == 1:
        print("✅ Только один обработчик setup_wizard - это хорошо!")
        last_handler = setup_wizard_handlers[0]
        if 'wizards' in last_handler.function.__module__:
            print("✅ Активен новый обработчик из wizards.py")
        else:
            print("⚠️ Активен старый обработчик")
    elif len(setup_wizard_handlers) > 1:
        print("⚠️ Найдено несколько обработчиков setup_wizard!")
        print("Последний зарегистрированный (приоритетный):")
        last_handler = setup_wizard_handlers[-1]
        print(f"  {last_handler.function.__name__} из {last_handler.function.__module__}")
    else:
        print("❌ Обработчики setup_wizard не найдены")
        
except Exception as e:
    print(f"❌ Ошибка: {e}")

print("\n=== ТЕСТ ЗАВЕРШЕН ===")
