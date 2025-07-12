#!/usr/bin/env python3
def format_username(username):
    if not username:
        return username
    return username if username.startswith('@') else f'@{username}'

# Тестируем функцию
test_cases = [
    'kanaaleks',     # обычный username
    '@kanaaleks',    # уже с @
    '@@kanaaleks',   # с двойным @
    '',              # пустая строка
]

print("Тестирование функции format_username:")
for case in test_cases:
    result = format_username(case)
    print(f'Input: {repr(case)} -> Output: {repr(result)}')
