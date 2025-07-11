# config.py
import os

# --- Токены и ключи из переменных окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# --- ID и пути к файлам ---
BOSS_ID = int(os.getenv("BOSS_ID", "196614680"))
ADMIN_REPORT_CHAT_ID = int(os.getenv("ADMIN_REPORT_CHAT_ID", "-1002645821302"))
CHAT_CONFIG_FILE = 'chat_configs.json'
AD_TEMPLATES_FILE = 'ad_templates.json'

# --- Параметры смены ---
EXPECTED_VOICES_PER_SHIFT = int(os.getenv("EXPECTED_VOICES_PER_SHIFT", "15"))
VOICE_TIMEOUT_MINUTES = int(os.getenv("VOICE_TIMEOUT_MINUTES", "40"))
VOICE_MIN_DURATION_SECONDS = int(os.getenv("VOICE_MIN_DURATION_SECONDS", "7"))
VOICE_COOLDOWN_SECONDS = int(os.getenv("VOICE_COOLDOWN_SECONDS", "120"))
BREAK_DURATION_MINUTES = int(os.getenv("BREAK_DURATION_MINUTES", "15"))
BREAK_DELAY_MINUTES = int(os.getenv("BREAK_DELAY_MINUTES", "60"))

# --- Ссылка на Google Таблицу ---
GOOGLE_SHEET_LINK_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_KEY}/edit#gid=0" if GOOGLE_SHEET_KEY else ""
GOOGLE_SHEET_LINK_TEXT = "АНАЛИЗ РАБОТЫ ВЕДУЩИХ"

# --- Карта часовых поясов ---
TIMEZONE_MAP = {
    "-1": "Europe/Kaliningrad", "0": "Europe/Moscow", "+1": "Europe/Samara",
    "+2": "Asia/Yekaterinburg", "+3": "Asia/Omsk", "+4": "Asia/Krasnoyarsk",
    "+5": "Asia/Irkutsk", "+6": "Asia/Yakutsk", "+7": "Asia/Vladivostok",
    "+8": "Asia/Magadan", "+9": "Asia/Kamchatka"
}

# --- Ключевые слова из phrases.py (для удобства импорта в одном месте) ---
try:
    from phrases import BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, soviet_phrases, ACHIEVEMENTS
except ImportError:
    BREAK_KEYWORDS = ["перерыв", "отдых", "обед", "покурить", "отойду"]
    RETURN_CONFIRM_WORDS = ["вернулся", "на месте", "пришел", "тут"]
    soviet_phrases = { "accept": ["Принято."], "too_short": ["Коротко."] }
    ACHIEVEMENTS = {}
