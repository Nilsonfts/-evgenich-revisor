#!/usr/bin/env python3
# test_healthcheck.py
"""
Тест healthcheck эндпойнта для локальной отладки.
"""

import requests
import time
import sys

def test_healthcheck(url="http://localhost:8000", max_attempts=10):
    """Тестирует healthcheck эндпойнт."""
    print(f"🔍 Тестируем healthcheck: {url}")
    
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Попытка {attempt}/{max_attempts}...")
            
            # Тест корневого эндпойнта
            response = requests.get(f"{url}/", timeout=10)
            print(f"  Root endpoint: {response.status_code}")
            if response.status_code == 200:
                print(f"  Response: {response.json()}")
            
            # Тест health эндпойнта
            response = requests.get(f"{url}/health", timeout=10)
            print(f"  Health endpoint: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"  Status: {data.get('status')}")
                print(f"  Database: {data.get('database')}")
                print(f"  Bot running: {data.get('bot_running')}")
                print("✅ Healthcheck успешен!")
                return True
            else:
                print(f"  Error response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Соединение отклонено (сервер не запущен?)")
        except requests.exceptions.Timeout:
            print(f"  ⏰ Таймаут соединения")
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
        
        if attempt < max_attempts:
            print("  ⏳ Ожидание 3 секунды...")
            time.sleep(3)
    
    print("❌ Healthcheck не прошел")
    return False

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = test_healthcheck(url)
    sys.exit(0 if success else 1)
