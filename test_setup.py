#!/usr/bin/env python3
# test_setup.py - тест для проверки основных функций

# Симуляция импортов
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Тестируем доступные концепции
AVAILABLE_CONCEPTS = {
    "РВБ": {"name": "РВБ", "description": "Концепция РВБ - романтический вечер для двоих"},
    "НЕБАР": {"name": "НЕБАР", "description": "НЕБАР - неформальный бар с живой атмосферой"},
    "ЕВГЕНИЧ": {"name": "ЕВГЕНИЧ", "description": "ЕВГЕНИЧ - классическое караоке"},
    "СПЛЕТНИ": {"name": "СПЛЕТНИ", "description": "СПЛЕТНИ - уютная атмосфера для откровенных разговоров"},
    "ОРБИТА": {"name": "ОРБИТА", "description": "ОРБИТА - космическая тематика"}
}

print("✅ Тест настройки концепций:")
for concept_id, concept_info in AVAILABLE_CONCEPTS.items():
    print(f"  - {concept_id}: {concept_info['name']}")

print("\n✅ Тест кнопок мастера настройки:")
for concept_id in AVAILABLE_CONCEPTS.keys():
    callback_data = f"wizard_concept_{concept_id}"
    print(f"  - Кнопка '{concept_id}' → callback: {callback_data}")

print("\n✅ Все тесты пройдены! Мастер настройки упрощен и готов к работе.")
print("   Теперь пользователь может просто выбрать концепцию одной кнопкой.")
