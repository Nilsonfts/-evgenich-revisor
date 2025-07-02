# scheduler.py
import schedule
import time
import logging
import datetime
import pytz
import random

# Импортируем все необходимое из наших модулей
from state import chat_data, user_history, chat_configs
from config import (
    VOICE_TIMEOUT_MINUTES, BREAK_DURATION_MINUTES, GOOGLE_SHEET_LINK_TEXT,
    GOOGLE_SHEET_LINK_URL, ADMIN_REPORT_CHAT_ID, soviet_phrases, EXPECTED_VOICES_PER_SHIFT
)
from utils import get_chat_title, generate_detailed_report
from g_sheets import append_shift_to_google_sheet

def generate_analytical_summary(user_data: dict, shift_goal: int) -> str:
    """Создает краткую аналитическую сводку по работе ведущего."""
    plan_percent = (user_data.get('count', 0) / shift_goal * 100) if shift_goal > 0 else 0
    lates = user_data.get('late_returns', 0)
    
    # Проверяем, были ли паузы дольше полуторного таймаута
    has_long_pauses = any(delta > VOICE_TIMEOUT_MINUTES * 1.5 for delta in user_data.get('voice_deltas', []))

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

def send_end_of_shift_report_for_chat(bot, chat_id: int):
    """Формирует и отправляет финальный отчет по смене, затем очищает данные."""
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        logging.warning(f"Попытка закрыть смену в чате {chat_id}, но активной смены нет.")
        return

    main_user_data = data.get('users', {}).get(data.get('main_id'))
    if not main_user_data:
        logging.warning(f"Не найдены данные по ведущему в чате {chat_id}")
        return

    shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
    analytical_conclusion = generate_analytical_summary(main_user_data, shift_goal)
    
    # Отправляем данные в Google Таблицу
    append_shift_to_google_sheet(bot, chat_id, data, analytical_conclusion)
    
    report_lines = generate_detailed_report(chat_id, data)
    final_report_text = "\n".join(report_lines)
    
    final_report_with_recommendation = final_report_text + f"\n\n---\n🧠 **Рекомендация:**\n_{analytical_conclusion}_"
    
    try:
        bot.send_message(chat_id, final_report_with_recommendation)
    except Exception as e:
        logging.error(f"Не удалось отправить отчет в рабочий чат {chat_id}: {e}")

    if ADMIN_REPORT_CHAT_ID and chat_id != ADMIN_REPORT_CHAT_ID:
        try:
            link_markdown = f"[{GOOGLE_SHEET_LINK_TEXT}]({GOOGLE_SHEET_LINK_URL})" if GOOGLE_SHEET_LINK_URL else ""
            admin_report_header = f"📍 *Отчет из чата: {get_chat_title(bot, chat_id)}*\n"
            admin_report = f"{admin_report_header}{final_report_with_recommendation}\n\n{link_markdown}"
            bot.send_message(ADMIN_REPORT_CHAT_ID, admin_report)
        except Exception as e:
            logging.error(f"Не удалось отправить отчет в чат руководства: {e}")
    
    # Очистка данных после отправки отчета
    if chat_id in user_history:
        del user_history[chat_id]
    if chat_id in chat_data:
        del chat_data[chat_id]
    logging.info(f"Данные смены для чата {chat_id} очищены.")

def check_user_activity(bot):
    """Проверяет активность пользователей и отправляет напоминания."""
    now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
    for chat_id, data in list(chat_data.items()):
        if not data.get('main_id'):
            continue

        main_id = data['main_id']
        user_data = data.get('users', {}).get(main_id)
        if not user_data:
            continue

        # Напоминание о затянувшемся перерыве
        if user_data.get('on_break'):
            break_start_time = user_data.get('break_start_time')
            if break_start_time and (now_moscow - break_start_time).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                last_reminder = user_data.get('last_break_reminder_time')
                if not last_reminder or (now_moscow - last_reminder).total_seconds() > 120: # Напоминаем не чаще, чем раз в 2 минуты
                    try:
                        bot.send_message(chat_id, f"@{user_data['username']}, {random.choice(soviet_phrases.get('return_demand', ['Пора вернуться к работе!']))}")
                        user_data['last_break_reminder_time'] = now_moscow
                    except Exception as e:
                        logging.error(f"Не удалось отправить напоминание о перерыве в чат {chat_id}: {e}")
            continue

        # Напоминание о долгом отсутствии ГС
        last_voice_time = user_data.get('last_voice_time')
        if last_voice_time:
            inactive_minutes = (now_moscow - last_voice_time).total_seconds() / 60
            if inactive_minutes > VOICE_TIMEOUT_MINUTES and not user_data.get('voice_timeout_reminder_sent'):
                try:
                    bot.send_message(chat_id, f"@{user_data['username']}, {random.choice(soviet_phrases.get('voice_reminder', ['Вы давно не выходили в эфир.']))}")
                    user_data['voice_timeout_reminder_sent'] = True
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание о ГС в чат {chat_id}: {e}")

def check_for_shift_end(bot):
    """Проверяет, не наступило ли время окончания смены для какого-либо чата."""
    for chat_id, config in list(chat_configs.items()):
        tz_name = config.get('timezone', 'Europe/Moscow')
        end_time_str = config.get('end_time')
        if not end_time_str:
            continue
        
        try:
            local_tz = pytz.timezone(tz_name)
            now_local = datetime.datetime.now(local_tz)
            end_time_obj = datetime.datetime.strptime(end_time_str, '%H:%M').time()
            
            # Отправляем отчет через минуту после официального конца смены
            report_time_obj = (datetime.datetime.combine(now_local.date(), end_time_obj) + datetime.timedelta(minutes=1)).time()
            
            # Проверяем, что в этом чате есть активная смена
            if chat_data.get(chat_id, {}).get('main_id'):
                # Проверяем, что время совпадает и отчет за сегодня еще не отправлялся
                if now_local.time().strftime('%H:%M') == report_time_obj.strftime('%H:%M'):
                    last_report_date = chat_data[chat_id].get('last_report_date')
                    if last_report_date != now_local.date():
                        logging.info(f"Наступило время ({report_time_obj.strftime('%H:%M')}) для отчета в чате {chat_id} (ТЗ: {tz_name}).")
                        send_end_of_shift_report_for_chat(bot, chat_id)
                        # Помечаем, что отчет за сегодня отправлен, чтобы избежать дублирования
                        if chat_id in chat_data:
                            chat_data[chat_id]['last_report_date'] = now_local.date()
        except Exception as e:
            logging.error(f"Ошибка в check_for_shift_end для чата {chat_id}: {e}")


def run_scheduler(bot):
    """Основной цикл планировщика, который запускает фоновые проверки."""
    schedule.every(1).minutes.do(check_for_shift_end, bot=bot)
    schedule.every(1).minutes.do(check_user_activity, bot=bot)
    
    logging.info("Планировщик настроен и запущен.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"Критическая ошибка в цикле планировщика: {e}")
        time.sleep(1)
