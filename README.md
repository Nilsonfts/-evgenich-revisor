# 🎤 КАРАОКЕ РЕВИЗОР - TELEGRAM БОТ

> **Профессиональный бот для управления сменами караоке ведущих с поддержкой ролей и автоматизацией**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![SQLite](https://img.shields.io/badge/Database-SQLite-green.svg)](https://sqlite.org)
[![Telegram](https://img.shields.io/badge/Platform-Telegram-blue.svg)](https://telegram.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🌟 ОСОБЕННОСТИ

### 🎭 **МНОГОРОЛЕВАЯ СИСТЕМА**
- **Рабочие дни (Вс-Чт)**: 1 караоке ведущий
- **Выходные дни (Пт-Сб)**: 2 ведущих - караоке + МС аниматор
- **Автоматическое назначение** ролей по расписанию
- **Раздельная статистика** для каждой роли

### 🎛️ **ИНТЕРАКТИВНАЯ АДМИН-ПАНЕЛЬ**
- Управление через **кнопки** вместо команд
- **Безопасный доступ** только для администраторов
- **Мгновенное управление** ботом и настройками
- **Диагностика и мониторинг** в реальном времени

### ⚡ **ВЫСОКАЯ ПРОИЗВОДИТЕЛЬНОСТЬ**  
- **SQLite база данных** для быстрого доступа к данным
- **Автоматическая очистка** старых записей
- **Параллельное сохранение** в Google Таблицы
- **Потокобезопасность** для стабильной работы

### 🤖 **УМНАЯ АВТОМАТИЗАЦИЯ**
- **Распознавание голосовых** сообщений
- **Автоматический подсчет** активности
- **Уведомления о перерывах** и целях
- **Scheduled задачи** для обслуживания

## 🚀 БЫСТРЫЙ СТАРТ

### 📋 Системные требования
- Python 3.8+
- SQLite (встроен в Python)
- Telegram Bot Token

### ⚙️ Установка

1. **Клонируйте репозиторий:**
```bash
git clone https://github.com/Nilsonfts/-evgenich-revisor.git
cd -evgenich-revisor
```

2. **Установите зависимости:**
```bash
pip install -r requirements.txt
```

3. **Настройте конфигурацию:**
```bash
cp config.py.example config.py
# Отредактируйте config.py, добавьте ваш BOT_TOKEN
```

4. **Запустите бота:**
```bash
python main.py
```

## 🎯 ОСНОВНЫЕ КОМАНДЫ

### 👤 Для ведущих:

#### 🎬 **Начало смены:**
```
/start                  # Автоматическое назначение роли
/start караоке         # Стать караоке ведущим  
/start МС              # Стать МС аниматором (только ПТ-СБ)
```

#### 📊 **Отчеты и статистика:**
```
/check                 # Мой отчет по текущей смене
/промежуточный         # То же что /check
/сводка                # Общая статистика за все время
```

#### 🔄 **Управление сменой:**
```
/передать              # Передать смену (ответить на сообщение)
```

#### ☕ **Перерывы:**
```
Просто напишите: перерыв, обед, покурить, отдых
Возвращение: вернулся, готов, работаю
```

#### ❓ **Справка:**
```
/help                  # Подробная справка для ведущих
/роли                  # Информация о системе ролей
```

### ⚜️ Для администраторов:

#### 🎛️ **Интерактивная панель:**
```
/admin                 # Открыть админ-панель с кнопками
```

#### 🔧 **Управление ботом:**
```
/bot_off              # Выключить бота в чате
/bot_on               # Включить бота в чате
/bot_status           # Проверить статус бота
```

#### 📚 **Справка:**
```
/helpadmin            # Подробная справка для админов
```

## 🎭 СИСТЕМА РОЛЕЙ

### 📅 **Расписание по дням недели:**

| День недели | Роли | Цели |
|-------------|------|------|
| **Вс-Чт** | 🎤 Караоке ведущий | 15 голосовых |
| **Пт-Сб** | 🎤 Караоке ведущий<br>🎭 МС аниматор | 15 голосовых<br>10 голосовых |

### 🎤 **Роли и функции:**

#### 🎤 **КАРАОКЕ ВЕДУЩИЙ**
- Ведет основную программу
- Объявляет исполнителей и песни
- Взаимодействует с публикой
- Контролирует очередь

#### 🎭 **МС (ВЕДУЩИЙ-АНИМАТОР)**
- Развлекает между песнями
- Проводит игры и конкурсы  
- Создает атмосферу
- Работает в команде с караоке ведущим

### 🤖 **Автоматическое назначение:**
- В **рабочие дни** - автоматически караоке ведущий
- В **выходные** - можно выбрать роль или занять свободную
- **Умное распределение** - бот сам определяет доступные роли

## 🎛️ АДМИН-ПАНЕЛЬ

### 📱 **Интерфейс с кнопками:**

```
⚜️ ПАНЕЛЬ АДМИНИСТРАТОРА ⚜️
┌─────────────────────────────┐
│ 📊 Статус    │ 📈 Рейтинг   │
│ 🎭 Роли      │ ⚙️ Настройки │  
│ 🔄 Рестарт   │ 📝 Отчет     │
│ 🚨 Проблемы  │ 📜 Лог       │
│ 🟢 Бот вкл/выкл             │
│ 📢 Рассылка (BOSS)          │
│ ❌ Закрыть                   │
└─────────────────────────────┘
```

### 🔧 **Функции панели:**
- **📊 Статус** - текущее состояние смен
- **🎭 Роли** - управление ролями и расписанием  
- **📈 Рейтинг** - статистика ведущих
- **🔄 Рестарт** - перезапуск системы
- **🟢 Бот вкл/выкл** - управление состоянием бота
- **📢 Рассылка** - отправка во все чаты (только BOSS)

## 💾 БАЗА ДАННЫХ

### 🗄️ **Структура SQLite:**

```sql
shifts                 # Основные данные смен
user_shift_data       # Данные пользователей в сменах  
event_history         # История событий
voice_stats           # Статистика голосовых сообщений
bot_settings          # Настройки бота для чатов
role_schedule         # Конфигурация ролей по дням
```

### 🚀 **Преимущества:**
- **Быстрый доступ** к данным
- **Автоматическая очистка** старых записей (30+ дней)
- **Резервирование** в Google Таблицы
- **Индексы** для оптимизации запросов

## 🔧 АРХИТЕКТУРА

### 📁 **Структура проекта:**

```
/workspaces/-evgenich-revisor/
├── main.py                 # 🚀 Точка входа приложения
├── config.py              # ⚙️ Конфигурация бота
├── database.py            # 💾 Работа с SQLite базой
├── models.py              # 📊 Модели данных
├── roles.py               # 🎭 Система ролей
├── admin_panel.py         # 🎛️ Интерактивная админ-панель
├── help_system.py         # 📚 Система справки
├── handlers.py            # 🔄 Основные обработчики
├── handlers/              # 📁 Модульные обработчики
│   ├── admin.py          # ⚜️ Админские команды
│   ├── shift.py          # 🎬 Управление сменами
│   ├── user.py           # 👤 Пользовательские команды
│   ├── voice.py          # 🎤 Обработка голосовых
│   └── ...
├── utils.py              # 🛠️ Утилиты
├── state_manager.py      # 💾 Управление состоянием
├── scheduler.py          # ⏰ Задачи по расписанию
├── phrases.py            # 💬 Фразы бота
├── requirements.txt      # 📦 Зависимости
└── data/                 # 📁 Данные
    ├── bot_database.db   # 💾 SQLite база
    └── ...
```

### 🔧 **Ключевые компоненты:**

#### 🎭 **Система ролей (roles.py):**
- Enum-based конфигурация ролей
- Автоматическое определение доступных ролей
- Гибкое расписание по дням недели

#### 🎛️ **Админ-панель (admin_panel.py):**
- Интерактивные inline-кнопки
- Безопасность через проверку прав
- Модульная архитектура функций

#### 💾 **База данных (database.py):**
- Потокобезопасные операции
- Автоматические индексы
- Методы очистки и оптимизации

#### 🔄 **Обработчики (handlers/):**
- Модульная структура
- Разделение ответственности
- Легкое расширение функциональности

## 📊 МОНИТОРИНГ И АНАЛИТИКА

### 📈 **Статистика:**
- **Голосовые сообщения** - количество и длительность
- **Перерывы** - частота и продолжительность
- **Опоздания** - после перерывов
- **Эффективность** - по ролям и дням

### 📋 **Отчеты:**
- **Личные отчеты** - для каждого ведущего
- **Общие сводки** - по чатам и периодам
- **Google Таблицы** - автоматическая выгрузка
- **Рейтинги** - лучшие ведущие

### 🔍 **Диагностика:**
- **Логирование событий** в базу
- **Мониторинг ошибок** через админ-панель
- **Статус системы** в реальном времени

## 🚀 РАЗВЕРТЫВАНИЕ

### 🐳 **Docker (рекомендуется):**
```bash
# Создать образ
docker build -t karaoke-revisor .

# Запустить контейнер
docker run -d --name karaoke-bot karaoke-revisor
```

### ☁️ **Облачные платформы:**
- **Railway** - готовая поддержка через nixpacks.toml
- **Heroku** - через Procfile
- **VPS** - прямой запуск

### 📦 **Nixpacks (Railway):**
```toml
[phases.setup]
nixPkgs = ["python310", "sqlite"]

[phases.install]
cmds = ["pip install -r requirements.txt"]

[start]
cmd = "python main.py"
```

## 🔧 НАСТРОЙКА

### ⚙️ **config.py:**
```python
# Основные настройки
BOT_TOKEN = "your_bot_token_here"
BOSS_ID = 123456789  # ID главного администратора

# Настройки перерывов
BREAK_DELAY_MINUTES = 30
BREAK_DURATION_MINUTES = 15

# Google Sheets (опционально)
GOOGLE_CREDENTIALS = "path/to/credentials.json"
SPREADSHEET_ID = "your_spreadsheet_id"
```

### 🗄️ **База данных:**
- Автоматическая инициализация при первом запуске
- Миграции выполняются автоматически
- Резервное копирование в data/

## 🤝 УЧАСТИЕ В РАЗРАБОТКЕ

### 🐛 **Сообщить об ошибке:**
1. Опишите проблему в Issues
2. Приложите логи из админ-панели
3. Укажите версию Python и ОС

### 💡 **Предложить улучшение:**
1. Создайте Feature Request в Issues
2. Опишите желаемую функциональность
3. Предложите варианты реализации

### 🔧 **Внести изменения:**
1. Fork репозитория
2. Создайте feature branch
3. Внесите изменения с тестами
4. Создайте Pull Request

## 📝 ЛИЦЕНЗИЯ

MIT License - подробности в файле [LICENSE](LICENSE)

## 👨‍💻 АВТОР

**GitHub Copilot** - AI-powered coding assistant  
**Создано для**: Караоке-баров и развлекательных заведений

## 🙏 БЛАГОДАРНОСТИ

- **pyTelegramBotAPI** - за отличную библиотеку для Telegram
- **SQLite** - за быстрою и надежную базу данных  
- **Google Sheets API** - за интеграцию с таблицами
- **Сообществу разработчиков** - за поддержку и идеи

---

### 🎉 **Желаем успешных смен и довольных гостей!**

> Если бот помог вашему заведению - поставьте ⭐ звезду проекту!
