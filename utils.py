"""Minimal utils.py to break cyclic imports and let the bot run.

Extend with real implementations later.
"""
import json

# --- Basic helpers -------------------------------------------------------

def get_chat_title(chat_id: int) -> str:
    """Return chat title; placeholder implementation."""
    return str(chat_id)

def is_admin(bot, user_id: int, chat_id: int) -> bool:
    """Simplified admin check – always True for now."""
    return True

def load_json_data(filepath: str, default):
    """Safe JSON loader that never crashes."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

# --- Lazy import proxy ----------------------------------------------------

def get_sheet(*args, **kwargs):
    """Lazy proxy to g_sheets.get_sheet to avoid circular import."""
    from g_sheets import get_sheet as _get_sheet
    return _get_sheet(*args, **kwargs)
