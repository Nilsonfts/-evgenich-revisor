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
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден"
    echo "💡 Скопируйте .env.example в .env и настройте BOT_TOKEN"
    cp .env.example .env
    echo "✅ Создан файл .env из шаблона"
    echo "⚠️  ВНИМАНИЕ: Настройте BOT_TOKEN в файле .env перед запуском!"
fi

# Проверяем BOT_TOKEN в .env
if ! grep -q "BOT_TOKEN.*=" .env || grep -q "BOT_TOKEN=YOUR_BOT_TOKEN_HERE" .env; then
    echo "⚠️  Внимание: BOT_TOKEN не настроен в .env"
    echo "💡 Добавьте ваш BOT_TOKEN в .env файл"
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
export BOT_TOKEN="test:token"  # Временный токен для инициализации БД
python3 -c "from database import db; print('✅ База данных инициализирована')" 2>/dev/null || echo "⚠️ База данных будет инициализирована при первом запуске"

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
