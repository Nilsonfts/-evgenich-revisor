# models.py

-from dataclasses import dataclass, field from typing import List, Optional, Dict import datetime
+from dataclasses import dataclass, field
+from typing import List, Optional, Dict
+import datetime
+import pytz

@dataclass
class UserData:
    """Класс для хранения данных о пользователе на смене."""
    user_id: int
    username: str
    count: int = 0
    on_break: bool = False
    breaks_count: int = 0
    late_returns: int = 0
    last_voice_time: Optional[str] = None
    last_break_time: Optional[str] = None
    break_start_time: Optional[str] = None
    last_activity_reminder_time: Optional[str] = None
    last_break_reminder_time: Optional[str] = None
    recognized_ads: List[str] = field(default_factory=list)
    voice_deltas: List[float] = field(default_factory=list)
    voice_durations: List[int] = field(default_factory=list)

@dataclass
class ShiftData:
    """Класс для хранения данных о текущей смене в чате."""
    main_id: Optional[int] = None
    users: Dict[int, UserData] = field(default_factory=dict)
    main_username: str = 'N/A'
    shift_start: str = field(default_factory=lambda: datetime.datetime.now(pytz.timezone('Europe/Moscow')).isoformat())
    shift_goal: int = 0
    last_report_date: Optional[str] = None
