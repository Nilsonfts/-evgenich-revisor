# database_manager.py
import logging
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import asdict
from models import ShiftData, UserData

# Импорты для SQLAlchemy
try:
    from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, Float, JSON
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.dialects.postgresql import UUID
    import uuid
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    logging.warning("SQLAlchemy не установлен, используется SQLite")

# Fallback на старую реализацию
if not SQLALCHEMY_AVAILABLE:
    from database import BotDatabase
    db = BotDatabase()
else:
    from config import DATABASE_URL, DB_TYPE
    
    # SQLAlchemy модели
    Base = declarative_base()
    
    class Shift(Base):
        __tablename__ = 'shifts'
        
        chat_id = Column(Integer, primary_key=True)
        main_id = Column(Integer)
        main_username = Column(String(255))
        shift_goal = Column(Integer, default=15)
        shift_start_time = Column(String(255))
        timezone = Column(String(100))
        status = Column(String(50), default='active')
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    class UserShiftData(Base):
        __tablename__ = 'user_shift_data'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        chat_id = Column(Integer)
        user_id = Column(Integer)
        username = Column(String(255))
        count = Column(Integer, default=0)
        role = Column(String(100))
        goal = Column(Integer, default=15)
        breaks_count = Column(Integer, default=0)
        late_returns = Column(Integer, default=0)
        on_break = Column(Boolean, default=False)
        break_start_time = Column(String(255))
        break_reminder_sent = Column(Boolean, default=False)
        last_voice_time = Column(String(255))
        last_activity_time = Column(String(255))
        recognized_ads = Column(Text)  # JSON string
        voice_deltas = Column(Text)    # JSON string
        voice_durations = Column(Text) # JSON string
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    class BotSettings(Base):
        __tablename__ = 'bot_settings'
        
        chat_id = Column(Integer, primary_key=True)
        enabled = Column(Boolean, default=True)
        admin_id = Column(Integer)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    class VoiceStats(Base):
        __tablename__ = 'voice_stats'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        chat_id = Column(Integer)
        user_id = Column(Integer)
        username = Column(String(255))
        duration = Column(Float)
        recognized_ad = Column(String(500))
        created_at = Column(DateTime, default=datetime.utcnow)
    
    class EventHistory(Base):
        __tablename__ = 'event_history'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        chat_id = Column(Integer)
        user_id = Column(Integer)
        username = Column(String(255))
        event_type = Column(String(100))
        event_data = Column(Text)
        created_at = Column(DateTime, default=datetime.utcnow)
    
    class RoleSchedule(Base):
        __tablename__ = 'role_schedule'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        chat_id = Column(Integer)
        day_of_week = Column(Integer)  # 0-6
        roles_config = Column(Text)    # JSON
        shift_goals = Column(Text)     # JSON
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Блокировка для потокобезопасности
    db_lock = threading.Lock()
    
    class PostgreSQLDatabase:
        """Класс для работы с PostgreSQL через SQLAlchemy."""
        
        def __init__(self, database_url: str = None):
            self.database_url = database_url or DATABASE_URL
            self.engine = create_engine(self.database_url)
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            self.init_database()
        
        def init_database(self):
            """Создает все таблицы."""
            with db_lock:
                Base.metadata.create_all(bind=self.engine)
                logging.info("База данных PostgreSQL инициализирована")
        
        def get_session(self) -> Session:
            """Возвращает новую сессию БД."""
            return self.SessionLocal()
        
        def set_bot_enabled(self, chat_id: int, enabled: bool, admin_id: int = None):
            """Включает/выключает бота для чата."""
            with db_lock:
                session = self.get_session()
                try:
                    setting = session.query(BotSettings).filter_by(chat_id=chat_id).first()
                    if setting:
                        setting.enabled = enabled
                        setting.admin_id = admin_id
                        setting.updated_at = datetime.utcnow()
                    else:
                        setting = BotSettings(
                            chat_id=chat_id,
                            enabled=enabled,
                            admin_id=admin_id
                        )
                        session.add(setting)
                    
                    session.commit()
                    logging.info(f"Бот {'включен' if enabled else 'выключен'} для чата {chat_id}")
                    
                except Exception as e:
                    session.rollback()
                    logging.error(f"Ошибка изменения состояния бота в БД: {e}")
                finally:
                    session.close()
        
        def is_bot_enabled(self, chat_id: int) -> bool:
            """Проверяет, включен ли бот для чата."""
            with db_lock:
                session = self.get_session()
                try:
                    setting = session.query(BotSettings).filter_by(chat_id=chat_id).first()
                    return setting.enabled if setting else True  # По умолчанию включен
                except Exception as e:
                    logging.error(f"Ошибка проверки состояния бота в БД: {e}")
                    return True  # По умолчанию включен
                finally:
                    session.close()
        
        def save_voice_stat(self, chat_id: int, user_id: int, username: str, duration: float, recognized_ad: str = ""):
            """Сохраняет статистику голосового сообщения."""
            with db_lock:
                session = self.get_session()
                try:
                    stat = VoiceStats(
                        chat_id=chat_id,
                        user_id=user_id,
                        username=username,
                        duration=duration,
                        recognized_ad=recognized_ad
                    )
                    session.add(stat)
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logging.error(f"Ошибка сохранения статистики голосового в БД: {e}")
                finally:
                    session.close()
        
        def save_event(self, chat_id: int, user_id: int, username: str, event_type: str, event_data: str):
            """Сохраняет событие в историю."""
            with db_lock:
                session = self.get_session()
                try:
                    event = EventHistory(
                        chat_id=chat_id,
                        user_id=user_id,
                        username=username,
                        event_type=event_type,
                        event_data=event_data
                    )
                    session.add(event)
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logging.error(f"Ошибка сохранения события в БД: {e}")
                finally:
                    session.close()
        
        def get_user_stats_from_db(self, user_id: int) -> Dict:
            """Получает статистику пользователя из базы данных."""
            with db_lock:
                session = self.get_session()
                try:
                    # Подсчитываем статистику из voice_stats
                    voice_count = session.query(VoiceStats).filter_by(user_id=user_id).count()
                    
                    # Подсчитываем смены
                    shifts_count = session.query(UserShiftData).filter_by(user_id=user_id).count()
                    
                    # Считаем перерывы и опоздания из событий
                    breaks_count = session.query(EventHistory).filter_by(
                        user_id=user_id, event_type='break_start'
                    ).count()
                    
                    lates_count = session.query(EventHistory).filter_by(
                        user_id=user_id, event_type='late_return'
                    ).count()
                    
                    return {
                        'shifts_count': shifts_count,
                        'total_voices': voice_count,
                        'total_breaks': breaks_count,
                        'total_lates': lates_count
                    }
                    
                except Exception as e:
                    logging.error(f"Ошибка получения статистики пользователя из БД: {e}")
                    return {'shifts_count': 0, 'total_voices': 0, 'total_breaks': 0, 'total_lates': 0}
                finally:
                    session.close()
        
        def cleanup_old_data(self, days_old: int = 30):
            """Очищает старые данные из базы."""
            with db_lock:
                session = self.get_session()
                try:
                    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
                    
                    # Очищаем старые голосовые статистики
                    session.query(VoiceStats).filter(VoiceStats.created_at < cutoff_date).delete()
                    
                    # Очищаем старые события
                    session.query(EventHistory).filter(EventHistory.created_at < cutoff_date).delete()
                    
                    session.commit()
                    logging.info(f"Очищены данные старше {days_old} дней")
                    
                except Exception as e:
                    session.rollback()
                    logging.error(f"Ошибка очистки старых данных: {e}")
                finally:
                    session.close()
    
    # Создаем экземпляр базы данных
    if DB_TYPE == "postgresql":
        db = PostgreSQLDatabase()
    else:
        # Fallback на SQLite
        from database import BotDatabase
        db = BotDatabase()
