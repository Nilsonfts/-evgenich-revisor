# Dockerfile
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код приложения
COPY . .

# Создаем папку для данных
RUN mkdir -p data

# Указываем переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Проверяем код при сборке
RUN python -m py_compile *.py handlers/*.py

# Экспортируем порт (если понадобится webhook)
EXPOSE 8080

# Команда по умолчанию
CMD ["python", "main.py"]

# Метаданные
LABEL maintainer="GitHub Copilot"
LABEL description="Караоке-ревизор Telegram бот с многоролевой системой"
LABEL version="2.0"
