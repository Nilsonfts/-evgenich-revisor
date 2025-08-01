# state.py
from typing import Dict, List
import threading

# Глобальные переменные, хранящие состояние бота в реальном времени
chat_data: Dict[int, dict] = {}
user_history: Dict[int, List[str]] = {}
chat_configs: Dict[int, dict] = {}
ad_templates: Dict[str, dict] = {}
user_states: Dict[int, dict] = {} # Для пошаговых сценариев (wizards)
pending_transfers: Dict[int, dict] = {} # Для предложений о передаче смены

# ДОБАВЛЕНО: Замок для потокобезопасного изменения данных
data_lock = threading.Lock()
