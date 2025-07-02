"""Comprehensive utils.py with minimal working implementations
to satisfy imports from handlers and break cyclic dependencies.
Extend real logic later.
"""

import json
import logging
from typing import Any, Dict

# --------------------------------------------------------
# Basic helpers & placeholders
# --------------------------------------------------------

def get_chat_title(chat_id: int) -> str:
    """Return chat title placeholder."""
    return str(chat_id)

def is_admin(bot, user_id: int, chat_id: int) -> bool:
    """Simplified admin check: everyone is admin by default."""
    return True

# Decorator factory requiring admin rights
def admin_required(bot):
    def decorator(func):
        def wrapper(message, *args, **kwargs):
            if is_admin(bot, message.from_user.id, message.chat.id):
                return func(message, *args, **kwargs)
            else:
                try:
                    bot.reply_to(message, "⛔️ Доступ только для администраторов.")
                except Exception:
                    pass
        return wrapper
    return decorator

# --------------------------------------------------------
# JSON persistence helpers
# --------------------------------------------------------

def load_json_data(filepath: str, default: Any):
    """Safe JSON loader. Returns *default* if file missing / invalid."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.warning("load_json_data: %s", e)
        return default

def save_json_data(filepath: str, data: Any) -> None:
    """Write data to JSON file, safe mode."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error("save_json_data: %s", e)

# --------------------------------------------------------
# Bot‑state helper stubs (expand later)
# --------------------------------------------------------

_users_state: Dict[int, Dict] = {}
_shift_state: Dict[int, Dict] = {}

def init_user_data(user_id: int) -> Dict:
    return _users_state.setdefault(user_id, {})

def init_shift_data(chat_id: int) -> Dict:
    return _shift_state.setdefault(chat_id, {})

def handle_user_return(user_id: int, chat_id: int):
    """Stub to mark user's return from break."""
    _users_state.setdefault(user_id, {}).update({"status": "present"})

def save_history_event(chat_id: int, text: str):
    """Log history event placeholder (prints to console)."""
    logging.info("HISTORY [%s]: %s", chat_id, text)

# --------------------------------------------------------
# Report helper
# --------------------------------------------------------

def get_full_report_text(report_data: Dict[str, Any]) -> str:
    lines = ["📋 Итоговый отчёт:\n"]
    for k, v in report_data.items():
        lines.append(f"• {k}: {v}")
    return "\n".join(lines)

# --------------------------------------------------------
# Lazy proxy to g_sheets to avoid cyclic import
# --------------------------------------------------------

def get_sheet(*args, **kwargs):
    from g_sheets import get_sheet as _get_sheet
    return _get_sheet(*args, **kwargs)

def get_username(user) -> str:
    """Возвращает username или fallback-строку."""
    return f"@{user.username}" if getattr(user, "username", None) else f"{user.first_name}"
