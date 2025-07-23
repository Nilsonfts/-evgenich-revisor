#!/usr/bin/env python3
# test_bot_startup.py - Простой тест запуска бота

import sys
import os

print("=== ТЕСТ ЗАПУСКА БОТА ===")
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")

# Проверяем .env файл
if os.path.exists('.env'):
    print("✅ .env файл найден")
    with open('.env', 'r') as f:
        lines = f.readlines()
        for line in lines[:5]:
            if 'BOT_TOKEN' in line:
                print(f"✅ BOT_TOKEN: {line.strip()[:30]}...")
else:
    print("❌ .env файл не найден")

# Проверяем импорты
try:
    from dotenv import load_dotenv
    print("✅ python-dotenv импортирован")
    load_dotenv()
    
    bot_token = os.getenv('BOT_TOKEN')
    if bot_token and bot_token != 'YOUR_BOT_TOKEN_HERE':
        print(f"✅ BOT_TOKEN загружен: {bot_token[:10]}...")
    else:
        print("❌ BOT_TOKEN не настроен")
        
except ImportError as e:
    print(f"❌ Ошибка импорта dotenv: {e}")

# Проверяем telebot
try:
    import telebot
    print("✅ pyTelegramBotAPI импортирован")
except ImportError as e:
    print(f"❌ Ошибка импорта telebot: {e}")

# Проверяем основные модули
try:
    from config import BOT_TOKEN as config_token
    print(f"✅ config.py загружен, token: {config_token[:10] if config_token else 'None'}...")
except Exception as e:
    print(f"❌ Ошибка загрузки config.py: {e}")

try:
    from database import db
    print("✅ database.py загружен")
except Exception as e:
    print(f"❌ Ошибка загрузки database.py: {e}")

print("=== ТЕСТ ЗАВЕРШЕН ===")
