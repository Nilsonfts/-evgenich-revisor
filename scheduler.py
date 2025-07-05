# scheduler.py (ИСПРАВЛЕННАЯ И СТАБИЛЬНАЯ ВЕРСИЯ)
import schedule
import time
import logging
import datetime
import pytz
import random

# Импортируем все необходимое
from state import chat_data, user_history, chat_configs
from config import (
    VOICE_TIMEOUT_MINUTES, BREAK_DURATION_MINUTES, GOOGLE_SHEET_LINK_TEXT,
    GOOGLE_SHEET_LINK_URL, ADMIN_REPORT_CHAT_ID, soviet_phrases, EXPECTED_VOICES_PER_SHIFT
)
from utils import get_chat_title, generate_detailed_report, init_shift_data
from g_sheets import append_shift_to_google_sheet
from state_manager import save_state

def generate_analytical_summary(user_data: dict, shift_goal: int) -> str:
    """Создает краткую аналитическую сводку по работе ведущего."""
    plan_percent = (user_data.get('count', 0) / shift_goal * 100) if shift_goal > 0 else 0
    lates = user_data.get('late_returns', 0)
    
    # Берем таймаут из конфига чата или дефолтный для корректного анализа
    chat_timeout = chat_configs.get(str(user_data.get('chat_id')), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)
    has_long_pauses = any(delta > chat_timeout * 1.5 for delta in user_data.get('voice_deltas', []))

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
    """Формирует и отправляет финальный отчет по смене, затем сбрасывает данные."""
    logging.info(f"Начинаю процедуру закрытия смены для чата {chat_id}...")
    data = chat_data.get(chat_id)
    if not data or not data.get('main_id'):
        logging.warning(f"Попытка закрыть смену в чате {chat_id}, но активной смены нет.")
        return

    main_user_data = data.get('users', {}).get(data.get('main_id'))
    if not main_user_data:
        logging.warning(f"Не найдены данные по ведущему в чате {chat_id}")
        return

    try:
        # Добавляем chat_id в данные пользователя для корректного анализа
        main_user_data['chat_id'] = chat_id
        shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
        analytical_conclusion = generate_analytical_summary(main_user_data, shift_goal)
        
        # Шаг 1: Сохранение данных в Google Sheets
        append_shift_to_google_sheet(bot, chat_id, data, analytical_conclusion)
        
        # Шаг 2: Формирование текста отчета
        report_lines = generate_detailed_report(chat_id, data)
        final_report_text = "\n".join(report_lines)
        final_report_with_recommendation = final_report_text + f"\n\n---\n🧠 **Рекомендация:**\n_{analytical_conclusion}_"
        
        # ИЗМЕНЕНИЕ: Формируем ссылку один раз
        link_markdown = f"[{GOOGLE_SHEET_LINK_TEXT}]({GOOGLE_SHEET_LINK_URL})" if GOOGLE_SHEET_LINK_URL else ""

        # Шаг 3: Отправка отчета в рабочий чат
        # ИЗМЕНЕНИЕ: Добавляем ссылку и отключаем предпросмотр
        main_report_text = f"🏁 Смена завершена!\n\n{final_report_with_recommendation}\n\n{link_markdown}"
        bot.send_message(chat_id, main_report_text, parse_mode="Markdown", disable_web_page_preview=True)

        # Шаг 4: Отправка отчета в чат руководства
        if ADMIN_REPORT_CHAT_ID and str(chat_id) != str(ADMIN_REPORT_CHAT_ID):
            admin_report_header = f"📍 *Отчет из чата: {get_chat_title(bot, chat_id)}*\n"
            admin_report = f"{admin_report_header}{final_report_with_recommendation}\n\n{link_markdown}"
            # ИЗМЕНЕНИЕ: Отключаем предпросмотр
            bot.send_message(ADMIN_REPORT_CHAT_ID, admin_report, parse_mode="Markdown", disable_web_page_preview=True)
    
        logging.info(f"Данные смены для чата {chat_id} будут сброшены.")
        init_shift_data(chat_id) # Используем функцию сброса
        
        chat_data[chat_id]['last_report_date'] = datetime.date.today().isoformat()
        
    except Exception as e:
        logging.error(f"Произошла критическая ошибка при формировании отчета для чата {chat_id}: {e}", exc_info=True)
        bot.send_message(chat_id, "❌ Произошла ошибка при формировании финального отчета. Данные не были сброшены. Попробуйте снова или обратитесь к администратору.")


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

        # Проверка тех, кто на перерыве
        if user_data.get('on_break'):
            break_start_time_str = user_data.get('break_start_time')
            if break_start_time_str:
                break_start_time = datetime.datetime.fromisoformat(break_start_time_str)
                if (now_moscow - break_start_time).total_seconds() / 60 > BREAK_DURATION_MINUTES:
                    last_reminder_str = user_data.get('last_break_reminder_time')
                    if not last_reminder_str or (now_moscow - datetime.datetime.fromisoformat(last_reminder_str)).total_seconds() > 120:
                        try:
                            phrase = random.choice(soviet_phrases.get('return_demand_hard', ['Пора вернуться к работе!']))
                            bot.send_message(chat_id, f"@{user_data['username']}, {phrase}")
                            user_data['last_break_reminder_time'] = now_moscow.isoformat()
                        except Exception as e:
                            logging.error(f"Не удалось отправить напоминание о перерыве в чат {chat_id}: {e}")
            continue

        # Проверка неактивных в эфире
        last_voice_time_str = user_data.get('last_voice_time')
        if last_voice_time_str:
            last_voice_time = datetime.datetime.fromisoformat(last_voice_time_str)
            inactive_minutes = (now_moscow - last_voice_time).total_seconds() / 60
            
            chat_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)

            if inactive_minutes > chat_timeout:
                last_reminder_str = user_data.get('last_activity_reminder_time')
                
                should_remind = not last_reminder_str or \
                                (now_moscow - datetime.datetime.fromisoformat(last_reminder_str)).total_seconds() > 180

                if should_remind:
                    try:
                        phrase = random.choice(soviet_phrases.get('pace_reminder', ['Вы давно не выходили в эфир.']))
                        bot.send_message(chat_id, f"@{user_data['username']}, {phrase} (тишина уже {int(inactive_minutes)} мин.)")
                        user_data['last_activity_reminder_time'] = now_moscow.isoformat()
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
            
            if now_local.strftime('%H:%M') == end_time_str:
                if chat_data.get(chat_id, {}).get('main_id'):
                    last_report_date_str = chat_data[chat_id].get('last_report_date')
                    
                    if not last_report_date_str or last_report_date_str != now_local.date().isoformat():
                        logging.info(f"Наступило время ({end_time_str}) для отчета в чате {chat_id} (ТЗ: {tz_name}).")
                        send_end_of_shift_report_for_chat(bot, chat_id)
        except Exception as e:
            logging.error(f"Ошибка в check_for_shift_end для чата {chat_id}: {e}", exc_info=True)

def run_scheduler(bot):
    """Основной цикл планировщика, который запускает фоновые проверки."""
    schedule.every(1).minutes.do(check_for_shift_end, bot=bot)
    schedule.every(1).minutes.do(check_user_activity, bot=bot)
    schedule.every(5).minutes.do(save_state, chat_data=chat_data, user_history=user_history)
    
    logging.info("Планировщик настроен и запущен. Автосохранение активно.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.error(f"Критическая ошибка в цикле планировщика: {e}")
        time.sleep(1)
