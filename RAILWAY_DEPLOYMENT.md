# Railway Deployment Guide

## 🚀 Развертывание на Railway

### Настройка переменных окружения

В Railway Dashboard установите следующие переменные:

#### Обязательные переменные:
```
BOT_TOKEN=your_telegram_bot_token
```

#### Опциональные переменные:
```
GOOGLE_SHEET_KEY=your_google_sheet_key
GOOGLE_CREDENTIALS_JSON={"type": "service_account", ...}
OPENAI_API_KEY=your_openai_api_key
```

### Health Check

Бот автоматически запускает health check сервер на порту, который Railway назначает через переменную `PORT`.

Endpoint: `https://your-app.railway.app/health`

### Автоматический деплой

1. Подключите свой GitHub репозиторий к Railway
2. Каждый push в main ветку автоматически триггерит новый деплой
3. Логи доступны в Railway Dashboard

### Мониторинг

- Health check каждые 5 минут
- Автоматический рестарт при сбоях
- Логи доступны в реальном времени

### Файлы для Railway

- `railway.toml` - конфигурация Railway
- `nixpacks.toml` - настройки Nixpacks билдера
- `Dockerfile` - альтернативный способ деплоя
- `requirements.txt` - Python зависимости

### Проблемы и решения

**Проблема**: Бот не отвечает
**Решение**: Проверьте переменную BOT_TOKEN в Railway Dashboard

**Проблема**: Health check fail
**Решение**: Убедитесь что порт правильно настроен (Railway автоматически устанавливает PORT)

**Проблема**: Проблемы с timezone
**Решение**: Railway использует UTC, но бот автоматически конвертирует в московское время

### Команды для диагностики

После деплоя используйте команды бота:
- `/debug_config` - проверка конфигурации
- `/status` - статус планировщика
- `/report` - тест генерации отчетов
