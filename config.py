# config.py
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

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
# Смещения относительно Москвы (UTC+3)
import pytz

TIMEZONE_MAP = {
    "-1": pytz.timezone("Europe/Kaliningrad"),  # UTC+2 (МСК-1)
    "0": pytz.timezone("Europe/Moscow"),        # UTC+3 (МСК)
    "+1": pytz.timezone("Europe/Samara"),       # UTC+4 (МСК+1)
    "+2": pytz.timezone("Asia/Yekaterinburg"),  # UTC+5 (МСК+2) - Пермь, Екатеринбург
    "+3": pytz.timezone("Asia/Omsk"),           # UTC+6 (МСК+3)
    "+4": pytz.timezone("Asia/Krasnoyarsk"),    # UTC+7 (МСК+4)
    "+5": pytz.timezone("Asia/Irkutsk"),        # UTC+8 (МСК+5)
    "+6": pytz.timezone("Asia/Yakutsk"),        # UTC+9 (МСК+6)
    "+7": pytz.timezone("Asia/Vladivostok"),    # UTC+10 (МСК+7)
    "+8": pytz.timezone("Asia/Magadan"),        # UTC+11 (МСК+8)
    "+9": pytz.timezone("Asia/Kamchatka")       # UTC+12 (МСК+9)
}

# --- Ключевые слова из phrases.py (для удобства импорта в одном месте) ---
try:
    from phrases import BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, soviet_phrases, ACHIEVEMENTS
except ImportError:
    BREAK_KEYWORDS = ["перерыв", "отдых", "обед", "покурить", "отойду"]
    RETURN_CONFIRM_WORDS = ["вернулся", "на месте", "пришел", "тут"]
    soviet_phrases = { "accept": ["Принято."], "too_short": ["Коротко."] }
    ACHIEVEMENTS = {}
