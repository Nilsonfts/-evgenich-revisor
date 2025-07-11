# database.py
import sqlite3
import logging
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import asdict
from models import ShiftData, UserData

# Блокировка для потокобезопасности
db_lock = threading.Lock()

class BotDatabase:
    """Класс для работы с локальной базой данных SQLite."""
    
    def __init__(self, db_path: str = "data/bot_database.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализирует структуру базы данных."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица для данных смен
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS shifts (
                    chat_id INTEGER PRIMARY KEY,
                    main_id INTEGER,
                    main_username TEXT,
                    shift_goal INTEGER DEFAULT 15,
                    shift_start_time TEXT,
                    timezone TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для пользовательских данных в смене
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_shift_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    role TEXT DEFAULT 'караоке_ведущий',
                    count INTEGER DEFAULT 0,
                    breaks_count INTEGER DEFAULT 0,
                    late_returns INTEGER DEFAULT 0,
                    on_break BOOLEAN DEFAULT FALSE,
                    break_start_time TEXT,
                    break_reminder_sent BOOLEAN DEFAULT FALSE,
                    last_voice_time TEXT,
                    last_activity_time TEXT,
                    recognized_ads TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES shifts (chat_id)
                )
            ''')
            
            # Таблица для истории событий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS event_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    event_type TEXT,
                    event_description TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для статистики голосовых сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS voice_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    voice_duration REAL,
                    recognized_ad TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для настроек бота
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    chat_id INTEGER PRIMARY KEY,
                    enabled BOOLEAN DEFAULT TRUE,
                    admin_id INTEGER,
                    config_data TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для конфигурации ролей по дням недели
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS role_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    day_of_week INTEGER,
                    roles_config TEXT DEFAULT '[]',
                    shift_goals TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES shifts (chat_id)
                )
            ''')
            
            # Индексы для оптимизации
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_shift_chat_user ON user_shift_data (chat_id, user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_history_chat_time ON event_history (chat_id, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_voice_stats_chat_time ON voice_stats (chat_id, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_role_schedule_chat_day ON role_schedule (chat_id, day_of_week)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_shift_role ON user_shift_data (chat_id, role)')
            
            # Добавляем колонку role, если её нет (для совместимости со старой БД)
            try:
                cursor.execute('ALTER TABLE user_shift_data ADD COLUMN role TEXT DEFAULT "караоке_ведущий"')
            except sqlite3.OperationalError:
                pass  # Колонка уже существует
            
            conn.commit()
            conn.close()
            
        logging.info("База данных инициализирована успешно")
    
    def save_shift_data(self, chat_id: int, shift_data: ShiftData):
        """Сохраняет данные смены в базу данных."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Сохраняем основные данные смены
                cursor.execute('''
                    INSERT OR REPLACE INTO shifts 
                    (chat_id, main_id, main_username, shift_goal, shift_start_time, timezone, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    chat_id, shift_data.main_id, shift_data.main_username,
                    shift_data.shift_goal, shift_data.shift_start_time,
                    shift_data.timezone, 'active', datetime.now().isoformat()
                ))
                
                # Удаляем старые данные пользователей для этого чата
                cursor.execute('DELETE FROM user_shift_data WHERE chat_id = ?', (chat_id,))
                
                # Сохраняем данные пользователей
                for user_id, user_data in shift_data.users.items():
                    # Получаем роль пользователя
                    user_role = getattr(user_data, 'role', 'караоке_ведущий')
                    
                    cursor.execute('''
                        INSERT INTO user_shift_data 
                        (chat_id, user_id, username, role, count, breaks_count, late_returns, 
                         on_break, break_start_time, break_reminder_sent, last_voice_time, 
                         last_activity_time, recognized_ads, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        chat_id, user_id, user_data.username, user_role, user_data.count,
                        user_data.breaks_count, user_data.late_returns, user_data.on_break,
                        user_data.break_start_time, user_data.break_reminder_sent,
                        user_data.last_voice_time, user_data.last_activity_time,
                        json.dumps(user_data.recognized_ads), datetime.now().isoformat()
                    ))
                
                conn.commit()
                logging.info(f"Данные смены для чата {chat_id} сохранены в БД")
                
            except Exception as e:
                logging.error(f"Ошибка сохранения данных смены в БД: {e}")
                conn.rollback()
            finally:
                conn.close()
    
    def load_shift_data(self, chat_id: int) -> Optional[ShiftData]:
        """Загружает данные смены из базы данных."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Загружаем основные данные смены
                cursor.execute('SELECT * FROM shifts WHERE chat_id = ?', (chat_id,))
                shift_row = cursor.fetchone()
                
                if not shift_row:
                    return None
                
                # Загружаем данные пользователей
                cursor.execute('SELECT * FROM user_shift_data WHERE chat_id = ?', (chat_id,))
                user_rows = cursor.fetchall()
                
                # Собираем пользователей
                users = {}
                for row in user_rows:
                    user_data = UserData(
                        user_id=row[2],
                        username=row[3],
                        role=row[4] if len(row) > 4 and row[4] else 'караоке_ведущий',  # Роль
                        count=row[5] if len(row) > 5 else row[4],  # Смещение для count
                        breaks_count=row[6] if len(row) > 6 else row[5],
                        late_returns=row[7] if len(row) > 7 else row[6],
                        on_break=bool(row[8] if len(row) > 8 else row[7]),
                        break_start_time=row[9] if len(row) > 9 else row[8],
                        break_reminder_sent=bool(row[10] if len(row) > 10 else row[9]),
                        last_voice_time=row[11] if len(row) > 11 else row[10],
                        last_activity_time=row[12] if len(row) > 12 else row[11],
                        recognized_ads=json.loads(row[13] if len(row) > 13 and row[13] else row[12] or '[]')
                    )
                    users[row[2]] = user_data
                
                # Создаем объект смены
                shift_data = ShiftData(
                    main_id=shift_row[1],
                    main_username=shift_row[2],
                    shift_goal=shift_row[3],
                    shift_start_time=shift_row[4],
                    timezone=shift_row[5],
                    users=users
                )
                
                logging.info(f"Данные смены для чата {chat_id} загружены из БД")
                return shift_data
                
            except Exception as e:
                logging.error(f"Ошибка загрузки данных смены из БД: {e}")
                return None
            finally:
                conn.close()
    
    def save_event(self, chat_id: int, user_id: int, username: str, event_type: str, description: str):
        """Сохраняет событие в историю."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO event_history (chat_id, user_id, username, event_type, event_description)
                    VALUES (?, ?, ?, ?, ?)
                ''', (chat_id, user_id, username, event_type, description))
                
                conn.commit()
                
            except Exception as e:
                logging.error(f"Ошибка сохранения события в БД: {e}")
            finally:
                conn.close()
    
    def save_voice_stat(self, chat_id: int, user_id: int, username: str, duration: float, recognized_ad: str = ""):
        """Сохраняет статистику голосового сообщения."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO voice_stats (chat_id, user_id, username, voice_duration, recognized_ad)
                    VALUES (?, ?, ?, ?, ?)
                ''', (chat_id, user_id, username, duration, recognized_ad))
                
                conn.commit()
                
            except Exception as e:
                logging.error(f"Ошибка сохранения статистики голосового в БД: {e}")
            finally:
                conn.close()
    
    def set_bot_enabled(self, chat_id: int, enabled: bool, admin_id: int = None):
        """Включает/выключает бота для чата."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO bot_settings (chat_id, enabled, admin_id, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (chat_id, enabled, admin_id, datetime.now().isoformat()))
                
                conn.commit()
                logging.info(f"Бот {'включен' if enabled else 'выключен'} для чата {chat_id}")
                
            except Exception as e:
                logging.error(f"Ошибка изменения состояния бота в БД: {e}")
            finally:
                conn.close()
    
    def is_bot_enabled(self, chat_id: int) -> bool:
        """Проверяет, включен ли бот для чата."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('SELECT enabled FROM bot_settings WHERE chat_id = ?', (chat_id,))
                result = cursor.fetchone()
                return result[0] if result else True  # По умолчанию включен
                
            except Exception as e:
                logging.error(f"Ошибка проверки состояния бота в БД: {e}")
                return True  # По умолчанию включен
            finally:
                conn.close()
    
    def get_user_stats_from_db(self, user_id: int) -> Dict:
        """Получает статистику пользователя из базы данных."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Общая статистика по сменам
                cursor.execute('''
                    SELECT COUNT(*) as shifts_count,
                           SUM(count) as total_voices,
                           SUM(breaks_count) as total_breaks,
                           SUM(late_returns) as total_lates
                    FROM user_shift_data 
                    WHERE user_id = ?
                ''', (user_id,))
                
                result = cursor.fetchone()
                
                return {
                    'shifts_count': result[0] or 0,
                    'total_voices': result[1] or 0,
                    'total_breaks': result[2] or 0,
                    'total_lates': result[3] or 0
                }
                
            except Exception as e:
                logging.error(f"Ошибка получения статистики пользователя из БД: {e}")
                return {'shifts_count': 0, 'total_voices': 0, 'total_breaks': 0, 'total_lates': 0}
            finally:
                conn.close()
    
    def cleanup_old_data(self, days_old: int = 30):
        """Очищает старые данные из базы."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Удаляем старые события
                cursor.execute('''
                    DELETE FROM event_history 
                    WHERE timestamp < datetime('now', '-{} days')
                '''.format(days_old))
                
                # Удаляем старую статистику голосовых (оставляем только за последний месяц)
                cursor.execute('''
                    DELETE FROM voice_stats 
                    WHERE timestamp < datetime('now', '-{} days')
                '''.format(days_old))
                
                conn.commit()
                logging.info(f"Очищены данные старше {days_old} дней")
                
            except Exception as e:
                logging.error(f"Ошибка очистки старых данных: {e}")
            finally:
                conn.close()

    def set_role_schedule(self, chat_id: int, day_of_week: int, roles_config: List[str], shift_goals: Dict[str, int]):
        """Устанавливает конфигурацию ролей для определенного дня недели."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO role_schedule 
                    (chat_id, day_of_week, roles_config, shift_goals, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    chat_id, day_of_week, json.dumps(roles_config), 
                    json.dumps(shift_goals), datetime.now().isoformat()
                ))
                
                conn.commit()
                logging.info(f"Конфигурация ролей для чата {chat_id}, день {day_of_week} обновлена")
                
            except Exception as e:
                logging.error(f"Ошибка сохранения конфигурации ролей: {e}")
            finally:
                conn.close()

    def get_role_schedule(self, chat_id: int, day_of_week: int) -> Tuple[List[str], Dict[str, int]]:
        """Получает конфигурацию ролей для определенного дня недели."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT roles_config, shift_goals FROM role_schedule 
                    WHERE chat_id = ? AND day_of_week = ?
                ''', (chat_id, day_of_week))
                
                result = cursor.fetchone()
                if result:
                    roles = json.loads(result[0]) if result[0] else ["караоке_ведущий"]
                    goals = json.loads(result[1]) if result[1] else {"караоке_ведущий": 15}
                    return roles, goals
                else:
                    # Дефолтная конфигурация
                    return ["караоке_ведущий"], {"караоке_ведущий": 15}
                
            except Exception as e:
                logging.error(f"Ошибка получения конфигурации ролей: {e}")
                return ["караоке_ведущий"], {"караоке_ведущий": 15}
            finally:
                conn.close()

    def get_stats_by_role(self, user_id: int, role: str) -> Dict:
        """Получает статистику пользователя по конкретной роли."""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT COUNT(*) as shifts_count,
                           SUM(count) as total_voices,
                           SUM(breaks_count) as total_breaks,
                           SUM(late_returns) as total_lates
                    FROM user_shift_data 
                    WHERE user_id = ? AND role = ?
                ''', (user_id, role))
                
                result = cursor.fetchone()
                
                return {
                    'role': role,
                    'shifts_count': result[0] or 0,
                    'total_voices': result[1] or 0,
                    'total_breaks': result[2] or 0,
                    'total_lates': result[3] or 0
                }
                
            except Exception as e:
                logging.error(f"Ошибка получения статистики по роли: {e}")
                return {'role': role, 'shifts_count': 0, 'total_voices': 0, 'total_breaks': 0, 'total_lates': 0}
            finally:
                conn.close()

# Глобальный экземпляр базы данных
db = BotDatabase()
