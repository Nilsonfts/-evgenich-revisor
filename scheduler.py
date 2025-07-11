# scheduler.py
import schedule
import time
import logging
import datetime
import pytz
import random

from state import chat_data, user_history, chat_configs, data_lock
from config import (
    VOICE_TIMEOUT_MINUTES, BREAK_DURATION_MINUTES, GOOGLE_SHEET_LINK_TEXT,
    GOOGLE_SHEET_LINK_URL, ADMIN_REPORT_CHAT_ID, soviet_phrases, EXPECTED_VOICES_PER_SHIFT
)
from utils import get_chat_title, generate_detailed_report, init_shift_data
from g_sheets import append_shift_to_google_sheet
from state_manager import save_state
from models import UserData
from database import db  # Импортируем базу данных

# --- Аналитические функции ---

def generate_analytical_summary(user_data: UserData, shift_goal: int, chat_id: int) -> str:
    """Создает краткую аналитическую сводку по работе ведущего."""
    if shift_goal > 0:
        plan_percent = (user_data.count / shift_goal * 100)
    else:
        plan_percent = 100 # Если план 0, считаем его выполненным

    lates = user_data.late_returns
    chat_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)
    has_long_pauses = any(delta > chat_timeout * 1.5 for delta in user_data.voice_deltas)

    if plan_percent < 50:
        return f"❗️ Критическое невыполнение плана ({plan_percent:.0f}%). Требуется срочная беседа."
    if plan_percent < 80 and lates > 0:
        return f"❗️ Системные проблемы. План не выполнен ({plan_percent:.0f}%) и есть опоздания. Рекомендуется взять сотрудника на контроль."
    if plan_percent < 90:
        return f"⚠️ План не выполнен ({plan_percent:.0f}%). Необходимо выяснить причины."
    if lates > 0:
        return f"⚠️ Проблемы с дисциплиной. План выполнен, но зафиксировано {lates} опоздание(й). Рекомендуется провести беседу."
    if has_long_pauses:
        return f"✅ Хорошая работа, но есть замечание. План выполнен, однако были слишком длинные паузы. Стоит обратить внимание на ритмичность."
    
    return "✅ Отличная работа! Все показатели в норме. Можно ставить в пример."

# --- Основные функции планировщика ---

def send_end_of_shift_report_for_chat(bot, chat_id: int):
    """Потокобезопасно формирует и отправляет финальный отчет, затем сбрасывает данные."""
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    
    with data_lock:
        shift_data = chat_data.get(chat_id)
        if not shift_data or not shift_data.main_id:
            logging.warning(f"Попытка закрыть смену в чате {chat_id}, но активной смены нет.")
            return

        main_user_data = shift_data.users.get(shift_data.main_id)
        if not main_user_data:
            logging.warning(f"Не найдены данные по ведущему в чате {chat_id}")
            return
            
        # Копируем данные для безопасной работы вне блокировки
        shift_data_copy = shift_data
        
    # Все дальнейшие операции происходят с копией данных
    try:
        shift_goal = shift_data_copy.shift_goal
        analytical_conclusion = generate_analytical_summary(main_user_data, shift_goal, chat_id)
        
        append_shift_to_google_sheet(bot, chat_id, shift_data_copy, analytical_conclusion)
        
        report_lines = generate_detailed_report(chat_id, shift_data_copy)
        final_report_text = "\n".join(report_lines)
        final_report_with_recommendation = final_report_text + f"\n\n---\n🧠 **Рекомендация:**\n_{analytical_conclusion}_"
        
        link_markdown = f"[{GOOGLE_SHEET_LINK_TEXT}]({GOOGLE_SHEET_LINK_URL})" if GOOGLE_SHEET_LINK_URL else ""
        main_report_text = f"🏁 Смена завершена!\n\n{final_report_with_recommendation}\n\n{link_markdown}"
        
        bot.send_message(chat_id, main_report_text, parse_mode="Markdown", disable_web_page_preview=True)

        if ADMIN_REPORT_CHAT_ID and str(chat_id) != str(ADMIN_REPORT_CHAT_ID):
            admin_report_header = f"📍 *Отчет из чата: {get_chat_title(bot, chat_id)}*\n"
            admin_report = f"{admin_report_header}{final_report_with_recommendation}\n\n{link_markdown}"
            bot.send_message(ADMIN_REPORT_CHAT_ID, admin_report, parse_mode="Markdown", disable_web_page_preview=True)
    
        logging.info(f"Данные смены для чата {chat_id} будут сброшены.")
        
        with data_lock:
            last_report_date = datetime.date.today().isoformat()
            init_shift_data(chat_id) 
            if chat_id in chat_data:
                chat_data[chat_id].last_report_date = last_report_date
        
    except Exception as e:
        logging.error(f"Критическая ошибка при формировании отчета для чата {chat_id}: {e}", exc_info=True)
        try:
            bot.send_message(chat_id, "❌ Произошла ошибка при формировании финального отчета. Данные не были сброшены. Попробуйте снова или обратитесь к администратору.")
        except Exception as report_err:
            logging.error(f"Не удалось отправить сообщение об ошибке в чат {chat_id}: {report_err}")


def check_user_activity(bot):
    """Проверяет активность пользователей и отправляет напоминания."""
    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    
    with data_lock:
        # Создаем копию для итерации, чтобы избежать проблем при изменении словаря
        active_shifts = list(chat_data.items())

    for chat_id, shift_data in active_shifts:
        if not shift_data.main_id or not (user_data := shift_data.users.get(shift_data.main_id)):
            continue

        # Проверка тех, кто на перерыве
        if user_data.on_break and user_data.break_start_time:
            break_start_time = datetime.datetime.fromisoformat(user_data.break_start_time)
            if (now_moscow - break_start_time).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                last_reminder_str = user_data.last_break_reminder_time
                if not last_reminder_str or (now_moscow - datetime.datetime.fromisoformat(last_reminder_str)).total_seconds() > 120:
                    try:
                        phrase = random.choice(soviet_phrases.get('return_demand_hard', ['Пора вернуться к работе!']))
                        bot.send_message(chat_id, f"@{user_data.username}, {phrase}")
                        with data_lock:
                            user_data.last_break_reminder_time = now_moscow.isoformat()
                    except Exception as e:
                        logging.error(f"Не удалось отправить напоминание о перерыве в чат {chat_id}: {e}")
            continue

        # Проверка неактивных в эфире
        if user_data.last_voice_time:
            last_voice_time = datetime.datetime.fromisoformat(user_data.last_voice_time)
            inactive_minutes = (now_moscow - last_voice_time).total_seconds() / 60
            
            chat_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)

            if inactive_minutes > chat_timeout:
                last_reminder_str = user_data.last_activity_reminder_time
                should_remind = not last_reminder_str or (now_moscow - datetime.datetime.fromisoformat(last_reminder_str)).total_seconds() > 180

                if should_remind:
                    try:
                        phrase = random.choice(soviet_phrases.get('pace_reminder', ['Вы давно не выходили в эфир.']))
                        bot.send_message(chat_id, f"@{user_data.username}, {phrase} (тишина уже {int(inactive_minutes)} мин.)")
                        with data_lock:
                             user_data.last_activity_reminder_time = now_moscow.isoformat()
                    except Exception as e:
                        logging.error(f"Не удалось отправить напоминание о ГС в чат {chat_id}: {e}")

def check_for_shift_end(bot):
    """Проверяет, не наступило ли время окончания смены для какого-либо чата."""
    # Создаем копию для безопасной итерации
    configs_copy = list(chat_configs.items())

    for chat_id_str, config in configs_copy:
        tz_name = config.get('timezone', 'Europe/Moscow')
        end_time_str = config.get('end_time')
        if not end_time_str:
            continue
        
        try:
            local_tz = pytz.timezone(tz_name)
            now_local = datetime.datetime.now(local_tz)
            
            if now_local.strftime('%H:%M') == end_time_str:
                with data_lock:
                    current_shift = chat_data.get(int(chat_id_str))
                    # Проверяем, что смена активна и что отчет за сегодня еще не отправлялся
                    if current_shift and current_shift.main_id and (not current_shift.last_report_date or current_shift.last_report_date != now_local.date().isoformat()):
                        # Выносим вызов за пределы блокировки
                        chat_id_to_report = int(chat_id_str)
                    else:
                        chat_id_to_report = None
                
                if chat_id_to_report:
                    logging.info(f"Наступило время ({end_time_str}) для отчета в чате {chat_id_to_report} (ТЗ: {tz_name}).")
                    send_end_of_shift_report_for_chat(bot, chat_id_to_report)

        except Exception as e:
            logging.error(f"Ошибка в check_for_shift_end для чата {chat_id_str}: {e}", exc_info=True)

def database_cleanup_task():
    """Задача очистки старых данных из базы."""
    try:
        logging.info("Запуск задачи очистки базы данных...")
        db.cleanup_old_data(days_old=30)  # Удаляем данные старше 30 дней
        logging.info("Очистка базы данных завершена успешно")
    except Exception as e:
        logging.error(f"Ошибка при очистке базы данных: {e}")

def schedule_database_cleanup():
    """Планирует ежедневную очистку базы данных в 03:00."""
    schedule.every().day.at("03:00").do(database_cleanup_task)
    logging.info("Запланирована ежедневная очистка базы данных в 03:00")

def run_scheduler(bot):
    """Основной цикл планировщика, который запускает фоновые проверки."""
    schedule.every(1).minutes.do(check_for_shift_end, bot=bot)
    schedule.every(1).minutes.do(check_user_activity, bot=bot)
    # ИЗМЕНЕНО: Передаем bot в функцию сохранения, чтобы она могла уведомить об ошибке
    schedule.every(5).minutes.do(save_state, bot=bot, chat_data=chat_data, user_history=user_history)
    
    # Планируем очистку базы данных
    schedule_database_cleanup()
    
    logging.info("Планировщик настроен и запущен. Автосохранение активно.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"Критическая ошибка в цикле планировщика: {e}", exc_info=True)
        time.sleep(1)
