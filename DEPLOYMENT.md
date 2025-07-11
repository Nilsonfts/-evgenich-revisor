# 🚀 РУКОВОДСТВО ПО РАЗВЕРТЫВАНИЮ

## 📋 БЫСТРЫЙ СТАРТ

### 1. **Локальная установка:**
```bash
# Клонируйте репозиторий
git clone https://github.com/Nilsonfts/-evgenich-revisor.git
cd -evgenich-revisor

# Запустите скрипт развертывания
./deploy.sh
```

### 2. **Docker развертывание:**
```bash
# Создайте config.py с вашим BOT_TOKEN
cp .env.example .env
# Отредактируйте .env

# Запустите через Docker Compose
docker-compose up -d
```

### 3. **Ручная установка:**
```bash
# Установите зависимости
pip3 install -r requirements.txt

# Создайте папку данных
mkdir -p data

# Настройте config.py
# Добавьте ваш BOT_TOKEN

# Запустите бота
python3 main.py
```

## ⚙️ НАСТРОЙКА

### **config.py:**
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Обязательно!
BOSS_ID = 123456789               # ID главного админа
```

### **Переменные окружения (.env):**
```bash
BOT_TOKEN=your_telegram_bot_token
BOSS_ID=123456789
BREAK_DELAY_MINUTES=30
```

## 🐳 DOCKER

### **Сборка образа:**
```bash
docker build -t karaoke-revisor .
```

### **Запуск контейнера:**
```bash
docker run -d \
  --name karaoke-revisor \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.py:/app/config.py \
  karaoke-revisor
```

### **Docker Compose (рекомендуется):**
```bash
# Настройте config.py и .env
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down
```

## ☁️ ОБЛАЧНОЕ РАЗВЕРТЫВАНИЕ

### **Railway:**
1. Подключите GitHub репозиторий
2. Добавьте переменные окружения:
   - `BOT_TOKEN`
   - `BOSS_ID`
3. Railway автоматически развернет через `nixpacks.toml`

### **Heroku:**
```bash
# Установите Heroku CLI
heroku create your-karaoke-bot

# Установите переменные
heroku config:set BOT_TOKEN=your_token
heroku config:set BOSS_ID=123456789

# Деплой
git push heroku main
```

### **VPS/сервер:**
```bash
# Клонируйте на сервер
git clone https://github.com/Nilsonfts/-evgenich-revisor.git

# Настройте systemd сервис
sudo cp karaoke-revisor.service /etc/systemd/system/
sudo systemctl enable karaoke-revisor
sudo systemctl start karaoke-revisor
```

## 🔧 ПРОВЕРКА РАБОТЫ

### **Тест базовых функций:**
```bash
# В группе Telegram:
/start          # Заступить на смену
/admin          # Админ-панель (только админы)
/help           # Справка
/роли           # Информация о ролях
```

### **Тест ролевой системы:**
```bash
# В будний день:
/start          # Должен назначить караоке ведущего

# В пятницу/субботу:
/start караоке  # Первый ведущий - караоке
/start МС       # Второй ведущий - МС аниматор
```

### **Проверка БД:**
```bash
# Проверка файла БД
ls -la data/bot_database.db

# Проверка структуры (SQLite3)
sqlite3 data/bot_database.db ".tables"
```

## 📊 МОНИТОРИНГ

### **Логи:**
```bash
# Просмотр логов Docker
docker-compose logs -f karaoke-revisor

# Системные логи
journalctl -u karaoke-revisor -f

# Файловые логи
tail -f data/bot.log
```

### **Состояние бота:**
- Используйте `/admin` → "📊 Статус" в Telegram
- Проверьте логи на ошибки
- Убедитесь что БД доступна

## 🛠️ ОБСЛУЖИВАНИЕ

### **Резервное копирование:**
```bash
# Создание бэкапа БД
cp data/bot_database.db backups/backup_$(date +%Y%m%d).db

# Автоматический бэкап (cron)
0 3 * * * cp /path/to/data/bot_database.db /path/to/backups/backup_$(date +\%Y\%m\%d).db
```

### **Обновление:**
```bash
# Остановите бота
docker-compose down

# Обновите код
git pull origin main

# Пересоберите и запустите
docker-compose up -d --build
```

### **Очистка данных:**
- Бот автоматически очищает данные старше 30 дней
- Ручная очистка через админ-панель
- Или прямо в БД: `DELETE FROM event_history WHERE timestamp < datetime('now', '-30 days')`

## 🚨 РЕШЕНИЕ ПРОБЛЕМ

### **Бот не отвечает:**
1. Проверьте BOT_TOKEN в config.py
2. Убедитесь что бот добавлен в группу как админ
3. Проверьте логи на ошибки

### **Роли не работают:**
1. Проверьте что БД инициализирована
2. Убедитесь что текущий день недели корректный
3. Проверьте таблицу role_schedule в БД

### **Админ-панель недоступна:**
1. Убедитесь что вы админ группы
2. Проверьте BOSS_ID в конфигурации
3. Убедитесь что команда `/admin` отправлена в группе

### **БД ошибки:**
1. Проверьте права доступа к папке data/
2. Убедитесь что SQLite доступен
3. Пересоздайте БД: удалите файл и перезапустите бота

## 📞 ПОДДЕРЖКА

- **GitHub Issues:** [Создать тикет](https://github.com/Nilsonfts/-evgenich-revisor/issues)
- **Документация:** README.md в репозитории
- **Примеры:** Файлы .example в проекте

---

## ✅ ЧЕКЛИСТ РАЗВЕРТЫВАНИЯ

- [ ] Получен BOT_TOKEN от @BotFather
- [ ] Настроен config.py или .env
- [ ] Установлены зависимости Python
- [ ] Создана папка data/
- [ ] Бот добавлен в группу как администратор
- [ ] Проверены команды /start и /admin
- [ ] Настроен мониторинг и бэкапы
- [ ] Протестирована система ролей

**🎉 Поздравляем! Караоке-ревизор готов к работе!**
