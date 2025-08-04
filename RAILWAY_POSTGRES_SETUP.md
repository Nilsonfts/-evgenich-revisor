# 🔗 ПОДКЛЮЧЕНИЕ POSTGRESQL НА RAILWAY

## 🎯 ИНСТРУКЦИЯ ПО НАСТРОЙКЕ

### 1. В Railway Dashboard:

1. **Откройте ваш проект evgenich-revisor**
2. **Перейдите в Variables (переменные окружения)**
3. **Добавьте подключение к PostgreSQL:**

### 2. Получите DATABASE_URL от PostgreSQL сервиса:

1. **Кликните на сервис Postgres**
2. **Перейдите во вкладку "Variables"**  
3. **Скопируйте значение `DATABASE_URL`**

Оно будет выглядеть примерно так:
```
postgresql://postgres:password@containers-us-west-xyz.railway.app:1234/railway
```

### 3. Установите переменные для бота:

В сервисе **-evgenich-revisor** добавьте:

```bash
# Обязательные переменные
BOT_TOKEN=your_telegram_bot_token_here
BOSS_ID=196614680
DATABASE_URL=postgresql://postgres:password@containers-us-west-xyz.railway.app:1234/railway

# Опциональные
OPENAI_API_KEY=your_openai_key_here
GOOGLE_SHEET_KEY=your_google_sheet_key_here
EXPECTED_VOICES_PER_SHIFT=15
VOICE_TIMEOUT_MINUTES=40
VOICE_MIN_DURATION_SECONDS=7
VOICE_COOLDOWN_SECONDS=120
BREAK_DURATION_MINUTES=15
BREAK_DELAY_MINUTES=60
```

### 4. Настройка сети Railway:

1. **В сервисе evgenich-revisor:**
   - Перейдите в Settings → Networking
   - Убедитесь что есть доступ к PostgreSQL сервису

2. **В сервисе Postgres:**
   - Перейдите в Settings → Networking  
   - Убедитесь что разрешены подключения от бота

### 5. Пересоберите проект:

После установки переменных Railway автоматически пересоберет проект.

## 🔄 ЧТО ИЗМЕНИЛОСЬ:

1. **✅ Добавлена поддержка PostgreSQL** через SQLAlchemy
2. **✅ Автоматическое переключение** SQLite ↔ PostgreSQL
3. **✅ Миграция схемы БД** при первом запуске
4. **✅ Совместимость** с существующим кодом

## 🧪 ПРОВЕРКА РАБОТЫ:

После деплоя проверьте логи Railway:
- Должно появиться сообщение "База данных PostgreSQL инициализирована"
- Бот должен запуститься без ошибок

## 🔍 ОТЛАДКА:

Если возникают проблемы:
1. Проверьте правильность DATABASE_URL
2. Убедитесь что PostgreSQL сервис запущен  
3. Проверьте сетевые настройки
4. Посмотрите логи обоих сервисов

После настройки все данные будут сохраняться в PostgreSQL! 🎉
