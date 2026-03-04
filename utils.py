# utils.py
import json
import logging
import os
import datetime
import pytz
import random
from telebot import types
from functools import wraps
from collections import Counter

# Импортируем переменные и данные из других модулей
from config import BOSS_ID, BREAK_DURATION_MINUTES, EXPECTED_VOICES_PER_SHIFT, soviet_phrases
from state import chat_data, user_history
# ИМПОРТИРУЕМ НАШИ НОВЫЕ МОДЕЛИ
from models import UserData, ShiftData
from database_manager import db  # Используем единый database manager

def safe_reply(bot, message, text, **kwargs):
    """Безопасный reply_to: если сообщение удалено, отправляет обычное сообщение."""
    try:
        return bot.reply_to(message, text, **kwargs)
    except Exception:
        try:
            return bot.send_message(message.chat.id, text, **kwargs)
        except Exception as e:
            logging.error(f"safe_reply: не удалось отправить сообщение в чат {message.chat.id}: {e}")
            return None


def load_json_data(filepath, default_value=None):  # noqa: B006
    """Загружает данные из JSON файла.

    Используем None как sentinel, чтобы избежать залипания изменяемого
    объекта между вызовами функции.
    """
    if default_value is None:
        default_value = {}

    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки файла {filepath}: {e}")
    return default_value

def save_json_data(filename, data):
    """Сохраняет словарь data в JSON-файл. Возвращает True при успехе, иначе False."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения {filename}: {e}")
        return False

def is_admin(bot, user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь админом чата."""
    if user_id == BOSS_ID:
        return True
    if chat_id > 0:
        return False
    try:
        return user_id in [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    except Exception as e:
        logging.warning(f"Не удалось проверить права админа для user {user_id} в чате {chat_id}: {e}")
        return False

def is_user_admin(user_id: int, chat_id: int, bot=None) -> bool:
    """Alias для is_admin с другим порядком параметров для совместимости."""
    # Если bot не передан, попробуем импортировать из main
    if bot is None:
        try:
            from main import bot
        except ImportError:
            return user_id == BOSS_ID
    return is_admin(bot, user_id, chat_id)

def admin_required(bot):
    """Декоратор для проверки прав администратора."""
    def decorator(func):
        @wraps(func)
        def wrapper(message):
            if not is_admin(bot, message.from_user.id, message.chat.id):
                return safe_reply(bot, message, "⛔️ Эта команда доступна только администраторам чата.")
            return func(message)
        return wrapper
    return decorator

def get_username(user: types.User) -> str:
    """Возвращает имя пользователя без символа @."""
    return user.username if user.username else user.first_name

def get_username_with_at(user: types.User) -> str:
    """Возвращает имя пользователя с символом @."""
    return f"@{user.username}" if user.username else user.first_name

def get_chat_title(bot, chat_id: int) -> str:
    """Получает название чата по его ID."""
    try:
        return bot.get_chat(chat_id).title or str(chat_id)
    except Exception:
        return str(chat_id)

# ИЗМЕНЕНО: Функция теперь возвращает объект класса UserData с поддержкой ролей
def init_user_data(user_id: int, username: str, role: str = "караоке_ведущий") -> UserData:
    """Создает пустую структуру данных для нового пользователя с указанной ролью."""
    return UserData(user_id=user_id, username=username, role=role)

# ИЗМЕНЕНО: Функция теперь работает с объектами ShiftData
def init_shift_data(chat_id: int):
    """Создает или сбрасывает структуру данных для смены в чате."""
    from state import chat_configs
    
    # Сохраняем дату последнего отчета, если она есть, перед сбросом
    last_report_date = None
    if chat_id in chat_data and chat_data[chat_id]:
        last_report_date = chat_data[chat_id].last_report_date

    # Создаем новый объект ShiftData
    new_shift = ShiftData()
    new_shift.shift_goal = chat_configs.get(str(chat_id), {}).get('default_goal', EXPECTED_VOICES_PER_SHIFT)
    new_shift.last_report_date = last_report_date # Восстанавливаем дату
    
    chat_data[chat_id] = new_shift
    
    if chat_id in user_history:
        user_history[chat_id].clear()


# ИЗМЕНЕНО: Функция теперь работает с объектами UserData
def handle_user_return(bot, chat_id: int, user_id: int):
    """Обрабатывает возвращение пользователя с перерыва, используя фразы из phrases.py."""
    shift = chat_data.get(chat_id)
    if not shift: return
    
    user = shift.users.get(user_id)
    if not user or not user.on_break: return
    
    now = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    
    if not user.break_start_time: return
    break_start_time = datetime.datetime.fromisoformat(user.break_start_time)
    
    break_duration_minutes = (now - break_start_time).total_seconds() / 60
    user.on_break = False
    
    if break_duration_minutes > BREAK_DURATION_MINUTES:
        user.late_returns += 1
        late_minutes = int(break_duration_minutes - BREAK_DURATION_MINUTES)
        
        phrase_template = random.choice(
            soviet_phrases.get("system_messages", {}).get('return_late', ["✅ {username}, с возвращением! Вы опоздали на {minutes} мин."])
        )
        # Используем username как есть, если он уже начинается с @, или добавляем @
        username_for_message = user.username if user.username.startswith('@') else f"@{user.username}" if user.username else user.username
        message_text = phrase_template.format(username=username_for_message, minutes=late_minutes)
        bot.send_message(chat_id, message_text)
        
    else:
        phrase_template = random.choice(
            soviet_phrases.get("system_messages", {}).get('return_on_time', ["👍 {username}, с возвращением! Молодец, что вернулись вовремя."])
        )
        # Используем username как есть, если он уже начинается с @, или добавляем @
        username_for_message = user.username if user.username.startswith('@') else f"@{user.username}" if user.username else user.username
        message_text = phrase_template.format(username=username_for_message)
        bot.send_message(chat_id, message_text)
        
    save_history_event(chat_id, user_id, user.username, f"Вернулся с перерыва (длительность {break_duration_minutes:.1f} мин)")


def save_history_event(chat_id: int, user_id: int, username: str, event_description: str):
    """Сохраняет событие в историю (JSON + база данных)."""
    timestamp = datetime.datetime.now(pytz.timezone('Europe/Moscow')).isoformat()
    
    # Сохраняем в память (для совместимости)
    if chat_id not in user_history:
        user_history[chat_id] = []
    
    event = {
        "user_id": user_id,
        "username": username,
        "timestamp": timestamp,
        "event": event_description
    }
    user_history[chat_id].append(event)
    
    # Сохраняем в базу данных
    try:
        db.save_event(chat_id, user_id, username, "shift_event", event_description)
    except Exception as e:
        logging.error(f"Ошибка сохранения события в БД: {e}")

def save_voice_statistics(chat_id: int, user_id: int, username: str, duration: float, recognized_ad: str = ""):
    """Сохраняет статистику голосового сообщения в базу данных."""
    try:
        db.save_voice_stat(chat_id, user_id, username, duration, recognized_ad)
    except Exception as e:
        logging.error(f"Ошибка сохранения статистики голосового в БД: {e}")

def get_user_stats_from_database(user_id: int) -> dict:
    """Получает статистику пользователя из базы данных."""
    try:
        return db.get_user_stats_from_db(user_id)
    except Exception as e:
        logging.error(f"Ошибка получения статистики пользователя из БД: {e}")
        return {'shifts_count': 0, 'total_voices': 0, 'total_breaks': 0, 'total_lates': 0}

def enhanced_user_stats_report(user_id: int, username: str) -> str:
    """Создает расширенный отчет статистики пользователя."""
    # Получаем данные из базы
    db_stats = get_user_stats_from_database(user_id)
    
    report_lines = [
        f"📊 **Расширенная статистика для {username}**\n",
        f"🏢 **Из локальной базы данных:**",
        f"👑 Смен отработано: {db_stats['shifts_count']}",
        f"🗣️ Голосовых записано: {db_stats['total_voices']}",
        f"☕ Перерывов взято: {db_stats['total_breaks']}",
        f"⏳ Опозданий с перерыва: {db_stats['total_lates']}"
    ]
    
    # Вычисляем средние показатели
    if db_stats['shifts_count'] > 0:
        avg_voices = db_stats['total_voices'] / db_stats['shifts_count']
        avg_breaks = db_stats['total_breaks'] / db_stats['shifts_count']
        report_lines.extend([
            f"\n📈 **Средние показатели:**",
            f"🎯 Голосовых за смену: {avg_voices:.1f}",
            f"☕ Перерывов за смену: {avg_breaks:.1f}"
        ])
    
    return "\n".join(report_lines)

# ИЗМЕНЕНО: Функция теперь работает с объектами ShiftData и UserData, поддержка мульти-ролей
def generate_detailed_report(chat_id: int, data: ShiftData) -> list:
    """Собирает текстовый отчет на основе данных о смене для ВСЕХ участников."""
    if not data.users:
        return ["Ошибка: нет данных о ведущих."]

    shift_start_dt = datetime.datetime.fromisoformat(data.shift_start_time)
    report_date = shift_start_dt.strftime('%d.%m.%Y')

    report_lines = [
        f"📋 **#ОтчетВедущего** ({report_date})",
    ]

    for user_id, user_data in data.users.items():
        if user_data.count == 0 and not user_data.on_break:
            continue  # Пропускаем пользователей без активности
        
        role = getattr(user_data, 'role', 'караоке_ведущий')
        from roles import get_role_emoji, get_role_description
        role_emoji = get_role_emoji(role)
        role_desc = get_role_description(role)
        
        shift_goal = getattr(user_data, 'goal', data.shift_goal)
        plan_percent = (user_data.count / shift_goal * 100) if shift_goal > 0 else 0
        avg_delta = sum(user_data.voice_deltas) / len(user_data.voice_deltas) if user_data.voice_deltas else 0
        max_pause = max(user_data.voice_deltas or [0])
        avg_duration = sum(user_data.voice_durations) / len(user_data.voice_durations) if user_data.voice_durations else 0

        report_lines.extend([
            f"\n---",
            f"{role_emoji} **Ведущий:** {user_data.username} ({role_desc})",
            f"**📊 Основная Статистика**",
            f"**Голосовых:** {user_data.count} из {shift_goal} ({plan_percent:.0f}%)",
            f"**Перерывов:** {user_data.breaks_count}",
            f"**Опозданий:** {user_data.late_returns}",
            f"**📈 Аналитика Активности**",
            f"**Средний ритм:** {avg_delta:.1f} мин/ГС" if avg_delta else "**Средний ритм:** Н/Д",
            f"**Макс. пауза:** {max_pause:.1f} мин." if max_pause else "**Макс. пауза:** Н/Д",
            f"**Ср. длина ГС:** {avg_duration:.1f} сек." if avg_duration else "**Ср. длина ГС:** Н/Д",
        ])
        
        ad_counts = Counter(user_data.recognized_ads)
        if ad_counts:
            report_lines.append("\n**📝 Анализ Контента**")
            for ad, count in ad_counts.items():
                report_lines.append(f"✔️ {ad} (x{count})")

    # Добавляем общие маркетинговые инсайты на основе первого ведущего (main)
    main_user_data = data.users.get(data.main_id)
    if main_user_data:
        shift_goal = getattr(main_user_data, 'goal', data.shift_goal)
        marketing_insights = generate_marketing_insights(main_user_data, shift_goal)
        if marketing_insights:
            report_lines.append(f"\n---\n**💡 Маркетинговые Инсайты**")
            report_lines.append(marketing_insights)
        
        business_recommendations = generate_business_recommendations(main_user_data, shift_goal, chat_id)
        if business_recommendations:
            report_lines.append(f"\n---\n**🎯 Рекомендации для Бизнеса**")
            report_lines.append(business_recommendations)
            
    return report_lines

def generate_marketing_insights(user_data: UserData, shift_goal: int) -> str:
    """Генерирует маркетинговые инсайты для бизнеса."""
    insights = []
    
    # Анализ выполнения плана
    plan_percent = (user_data.count / shift_goal * 100) if shift_goal > 0 else 0
    if plan_percent >= 100:
        insights.append("🎯 План перевыполнен! Отличная работа ведущего.")
    elif plan_percent >= 80:
        insights.append("✅ План почти выполнен, хороший результат.")
    elif plan_percent >= 60:
        insights.append("⚠️ План выполнен частично, требуется мотивация.")
    else:
        insights.append("🔴 План значительно недовыполнен, нужен анализ причин.")
    
    # Анализ ритма работы
    if user_data.voice_deltas:
        avg_delta = sum(user_data.voice_deltas) / len(user_data.voice_deltas)
        if avg_delta <= 3:
            insights.append("⚡ Высокий темп работы - отличная вовлеченность гостей.")
        elif avg_delta <= 5:
            insights.append("👍 Оптимальный ритм работы.")
        else:
            insights.append("🐌 Медленный ритм - возможно нужно больше активности.")
    
    # Анализ перерывов
    if user_data.breaks_count == 0:
        insights.append("💪 Работа без перерывов - высокая самоотдача.")
    elif user_data.breaks_count <= 2:
        insights.append("☕ Умеренные перерывы - хороший баланс.")
    else:
        insights.append("😴 Много перерывов - возможно нужна мотивация.")
    
    # Анализ контента
    if user_data.recognized_ads:
        ad_diversity = len(set(user_data.recognized_ads))
        if ad_diversity >= 4:
            insights.append("🎨 Отличное разнообразие контента!")
        elif ad_diversity >= 2:
            insights.append("📝 Хорошее разнообразие рекламных тем.")
        else:
            insights.append("🔄 Стоит расширить разнообразие контента.")
    
    return " ".join(insights) if insights else "Требуется больше данных для анализа."

def generate_business_recommendations(user_data: UserData, shift_goal: int, chat_id: int) -> str:
    """Генерирует бизнес-рекомендации."""
    recommendations = []
    
    plan_percent = (user_data.count / shift_goal * 100) if shift_goal > 0 else 0
    
    # Рекомендации по результатам
    if plan_percent < 70:
        recommendations.append("• Рассмотрите систему мотивации для ведущих")
        recommendations.append("• Проанализируйте загруженность заведения")
    elif plan_percent > 120:
        recommendations.append("• Рассмотрите увеличение целевых показателей")
        recommendations.append("• Возможно стоит добавить больше ведущих в пиковые часы")
    
    # Рекомендации по перерывам
    if user_data.late_returns > 0:
        recommendations.append("• Установите четкие правила по времени перерывов")
        recommendations.append("• Рассмотрите систему напоминаний")
    
    # Рекомендации по контенту
    if len(set(user_data.recognized_ads)) < 3:
        recommendations.append("• Обновите рекламные материалы")
        recommendations.append("• Проведите тренинг по разнообразию контента")
    
    return "\n".join(recommendations) if recommendations else "Текущие показатели в пределах нормы."
