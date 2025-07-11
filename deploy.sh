#!/bin/bash
# deploy.sh - Скрипт развертывания караоке-ревизор бота

echo "🚀 РАЗВЕРТЫВАНИЕ КАРАОКЕ-РЕВИЗОР БОТА"
echo "======================================"

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.8+"
    exit 1
fi

echo "✅ Python найден: $(python3 --version)"

# Создаем папку для данных
mkdir -p data
echo "✅ Папка data создана"

# Устанавливаем зависимости
echo "📦 Установка зависимостей..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Зависимости установлены"
else
    echo "❌ Ошибка установки зависимостей"
    exit 1
fi

# Проверяем конфигурацию
if [ ! -f "config.py" ]; then
    echo "❌ Файл config.py не найден"
    echo "💡 Создайте config.py на основе config.py.example"
    exit 1
fi

# Проверяем BOT_TOKEN в конфигурации
if ! grep -q "BOT_TOKEN.*=" config.py; then
    echo "⚠️  Внимание: BOT_TOKEN не настроен в config.py"
    echo "💡 Добавьте ваш BOT_TOKEN в config.py"
fi

echo "✅ Конфигурация проверена"

# Проверяем компиляцию
echo "🔧 Проверка кода..."
python3 -m py_compile *.py handlers/*.py

if [ $? -eq 0 ]; then
    echo "✅ Код скомпилирован без ошибок"
else
    echo "❌ Ошибки в коде"
    exit 1
fi

# Инициализируем базу данных
echo "💾 Инициализация базы данных..."
python3 -c "from database import db; print('✅ База данных инициализирована')"

# Запускаем бота
echo ""
echo "🎤 КАРАОКЕ-РЕВИЗОР ГОТОВ К ЗАПУСКУ!"
echo "======================================"
echo ""
echo "🎭 Новые возможности:"
echo "   • Многоролевые смены (караоке + МС в ПТ-СБ)"
echo "   • Интерактивная админ-панель (/admin)"
echo "   • SQLite база данных для производительности"
echo "   • Автоматическая система ролей"
echo ""
echo "🚀 Для запуска выполните:"
echo "   python3 main.py"
echo ""
echo "📚 Основные команды:"
echo "   /start - начать смену (автоматическое назначение роли)"
echo "   /admin - админ-панель (только для админов)"
echo "   /help  - подробная справка"
echo ""

# Предлагаем запуск
read -p "🚀 Запустить бота сейчас? (y/N): " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🎤 Запуск бота..."
    python3 main.py
fi
