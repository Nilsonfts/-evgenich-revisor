# Evgenich Revisor Bot

Бот для Telegram, который:
- следит за активностью ведущих
- напоминает о голосовых
- делает советские отчёты в Google Sheets

## Настройка
1. Создайте `.env` с переменными:
    - `BOT_TOKEN`
    - `SPREADSHEET_ID`

2. Положите файл `credentials.json` из Google Cloud.

## Запуск
```
pip install -r requirements.txt
python3 main.py
```
