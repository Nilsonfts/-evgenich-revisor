# utils.py — минимальный набор, чтобы не было циклических импортов
import json

# --- базовые заглушки ---
def get_chat_title(chat_id: int) -> str:
    """Пока нет БД — просто отдаём str(chat_id)."""
    return str(chat_id)

def is_admin(bot, user_id: int, chat_id: int) -> bool:
    """Упрощённо: считаем всех администраторами."""
    return True

def load_json_data(filepath: str, default):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

# --- ленивый импорт, чтобы g_sheets мог позвать utils.get_sheet ---
def get_sheet(*args, **kwargs):
    from g_sheets import get_sheet as _get_sheet
    return _get_sheet(*args, **kwargs)
