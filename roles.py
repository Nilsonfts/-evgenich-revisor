# roles.py
"""
Константы и конфигурация ролей для системы караоке
"""

from enum import Enum
from typing import Dict, List
import datetime

class UserRole(Enum):
    """Доступные роли пользователей"""
    KARAOKE_HOST = "караоке_ведущий"
    MC = "МС"
    
class DayType(Enum):
    """Типы дней недели"""
    WEEKDAY = "будний"  # вс-чт
    WEEKEND = "выходной"  # пт-сб

# Маппинг дней недели (0=понедельник, 6=воскресенье) на тип дня
DAY_TYPE_MAPPING = {
    0: DayType.WEEKDAY,  # понедельник
    1: DayType.WEEKDAY,  # вторник
    2: DayType.WEEKDAY,  # среда
    3: DayType.WEEKDAY,  # четверг
    4: DayType.WEEKEND,  # пятница
    5: DayType.WEEKEND,  # суббота
    6: DayType.WEEKDAY,  # воскресенье
}

# Дефолтная конфигурация ролей по типам дней
DEFAULT_ROLE_CONFIG = {
    DayType.WEEKDAY: {
        "roles": [UserRole.KARAOKE_HOST.value],
        "goals": {UserRole.KARAOKE_HOST.value: 15}
    },
    DayType.WEEKEND: {
        "roles": [UserRole.KARAOKE_HOST.value, UserRole.MC.value],
        "goals": {
            UserRole.KARAOKE_HOST.value: 15,
            UserRole.MC.value: 10
        }
    }
}

# Эмодзи для ролей
ROLE_EMOJIS = {
    UserRole.KARAOKE_HOST.value: "🎤",
    UserRole.MC.value: "🎭"
}

# Описания ролей
ROLE_DESCRIPTIONS = {
    UserRole.KARAOKE_HOST.value: "Караоке ведущий",
    UserRole.MC.value: "МС"
}

def get_current_day_type() -> DayType:
    """Возвращает тип текущего дня"""
    today = datetime.datetime.now().weekday()
    return DAY_TYPE_MAPPING[today]

def get_roles_for_day_type(day_type: DayType) -> List[str]:
    """Возвращает список ролей для типа дня"""
    return DEFAULT_ROLE_CONFIG[day_type]["roles"]

def get_goals_for_day_type(day_type: DayType) -> Dict[str, int]:
    """Возвращает цели для ролей в зависимости от типа дня"""
    return DEFAULT_ROLE_CONFIG[day_type]["goals"]

def get_role_emoji(role: str) -> str:
    """Возвращает эмодзи для роли"""
    return ROLE_EMOJIS.get(role, "👤")

def get_role_description(role: str) -> str:
    """Возвращает описание роли"""
    return ROLE_DESCRIPTIONS.get(role, role)

def is_weekend_shift() -> bool:
    """Проверяет, является ли текущий день выходным (пт-сб)"""
    return get_current_day_type() == DayType.WEEKEND

def get_available_roles_for_day(day_of_week: int):
    """Возвращает список доступных ролей для дня недели (0=Пн, 6=Вс)."""
    if day_of_week in [4, 5]:  # Пятница, Суббота
        return [UserRole.KARAOKE_HOST.value, UserRole.MC.value]
    return [UserRole.KARAOKE_HOST.value]

def get_default_role_goals(day_of_week: int):
    """Возвращает цели для ролей по умолчанию."""
    if day_of_week in [4, 5]:
        return {UserRole.KARAOKE_HOST.value: 15, UserRole.MC.value: 10}
    return {UserRole.KARAOKE_HOST.value: 15}
