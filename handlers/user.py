# handlers/user.py

import random
import datetime
import pytz
import logging
import pandas as pd
from collections import Counter
from telebot import types

from utils import get_username, get_username_with_at, is_admin, safe_reply
from state import chat_data
from g_sheets import get_sheet
from phrases import soviet_phrases

def register_user_handlers(bot):

    @bot.message_handler(commands=['промежуточный', 'check'])
    def handle_check(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        
        if not shift or not shift.main_id:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_not_started', ["Смена в этом чате еще не началась."]))
            return safe_reply(bot, message, phrase)
        
        # ИСПРАВЛЕНО: Проверяем, что пользователь участник смены (не только main_id)
        if user_id not in shift.users:
            return safe_reply(bot, message, "Вы не участвуете в текущей смене. Используйте /start для начала.")
            
        user_data = shift.users.get(user_id)
        if not user_data:
            return safe_reply(bot, message, "Не удалось найти ваши данные по текущей смене.")

        # Используем персональную цель пользователя (или общую цель смены)
        shift_goal = getattr(user_data, 'goal', shift.shift_goal)
        plan_percent = (user_data.count / shift_goal * 100) if shift_goal > 0 else 0
        
        # Показываем роль
        role = getattr(user_data, 'role', 'караоке_ведущий')
        from roles import get_role_emoji, get_role_description
        role_emoji = get_role_emoji(role)
        role_desc = get_role_description(role)
        
        plan_done = "\n🌟 _План выполнен! Ты сегодня сигма!_ 🐺" if plan_percent >= 100 else ""
        report_lines = [
            f"📋 *Промежуточный отчёт* ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
            f"🎭 **Роль:** {role_emoji} {role_desc}",
            f"🗣️ **Голосовых:** {user_data.count} из {shift_goal} ({plan_percent:.0f}%)",
            plan_done,
            f"☕ **Перерывов:** {user_data.breaks_count}",
            f"⏳ **Опозданий с перерыва:** {user_data.late_returns}"
        ]
        
        # Добавляем информацию о паузе, если активна
        if user_data.on_pause:
            now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
            pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
            elapsed = (now_moscow - pause_start).total_seconds() / 60
            remaining = max(0, 40 - elapsed)
            if remaining > 0:
                report_lines.append(f"⏸️ **ПАУЗА АКТИВНА:** осталось {int(remaining)} мин")
            else:
                # Пауза истекла, автоматически отключаем
                user_data.on_pause = False
                user_data.pause_end_time = now_moscow.isoformat()
                report_lines.append("⏯️ **Пауза завершена** автоматически!")
        
        ad_counts = Counter(user_data.recognized_ads)
        if ad_counts:
            report_lines.append("\n**📝 Анализ контента:**")
            for ad, count in ad_counts.items():
                report_lines.append(f"✔️ {ad} (x{count})")
        safe_reply(bot, message, "\n".join(report_lines), parse_mode="Markdown")

    @bot.message_handler(commands=['сводка'])
    def my_total_stats(message: types.Message):
        if not pd: return safe_reply(bot, message, "Модуль для анализа данных (pandas) не загружен.")
        
        user_id = message.from_user.id
        username = get_username_with_at(message.from_user)
        safe_reply(bot, message, f"📊 Собираю вашу общую статистику из Google Таблицы, {username}. Минутку...")
        
        worksheet = get_sheet()
        if not worksheet: return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице.")
        
        try:
            df = pd.DataFrame(worksheet.get_all_records())
            if df.empty or 'ID Ведущего' not in df.columns: return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")
            
            df['ID Ведущего'] = pd.to_numeric(df['ID Ведущего'], errors='coerce')
            user_df = df[df['ID Ведущего'] == user_id].copy()
            
            if user_df.empty: return bot.send_message(message.chat.id, f"{username}, не найдено ваших смен в общей статистике.")
            
            numeric_cols = ['Голосовых (шт)', 'Перерывов (шт)', 'Опозданий (шт)']
            for col in numeric_cols: 
                user_df[col] = pd.to_numeric(user_df[col], errors='coerce').fillna(0)

            total_shifts = len(user_df)
            total_voices = user_df['Голосовых (шт)'].sum()
            total_breaks = user_df['Перерывов (шт)'].sum()
            total_lates = user_df['Опозданий (шт)'].sum()
            
            report_text = (
                f"⭐️ Общая статистика для {username} ⭐️\n\n"
                f"👑 Всего смен отработано: {total_shifts}\n"
                f"🗣️ Всего голосовых записано: {int(total_voices)}\n"
                f"☕️ Всего перерывов: {int(total_breaks)}\n"
                f"⏳ Всего опозданий с перерыва: {int(total_lates)}"
            )
            bot.send_message(message.chat.id, report_text)
        except Exception as e:
            logging.error(f"Ошибка анализа Google Sheets для /сводка: {e}")
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('generic_error', ["Произошла ошибка при выполнении команды."]))
            bot.send_message(message.chat.id, phrase)

    @bot.message_handler(commands=['help', 'помощь'])
    def handle_help(message: types.Message):
        """Обработчик команды помощи."""
        from help_system import get_help_text
        help_text = get_help_text()
        bot.send_message(message.chat.id, help_text, parse_mode='Markdown')
    
    @bot.message_handler(commands=['helpadmin', 'adminhelp', 'админпомощь'])
    def handle_admin_help(message: types.Message):
        """Обработчик команды помощи для админов."""
        from utils import is_admin
        if not is_admin(bot, message.from_user.id, message.chat.id):
            return safe_reply(bot, message, "❌ Эта команда доступна только администраторам.")
        
        from help_system import get_admin_help_text
        help_text = get_admin_help_text()
        bot.send_message(message.chat.id, help_text, parse_mode='Markdown')
    
    @bot.message_handler(commands=['роли', 'roles'])
    def handle_roles_info(message: types.Message):
        """Обработчик команды информации о ролях."""
        from help_system import get_roles_help_text
        roles_text = get_roles_help_text()
        bot.send_message(message.chat.id, roles_text, parse_mode='Markdown')
    
    @bot.message_handler(commands=['commands', 'команды'])
    def handle_all_commands(message: types.Message):
        """Показывает полный список всех команд."""
        from commands_list import get_all_commands_list
        from utils import is_admin as check_admin
        
        is_admin_user = check_admin(bot, message.from_user.id, message.chat.id)
        commands_text = get_all_commands_list(is_admin_user)
        bot.send_message(message.chat.id, commands_text)
    
    @bot.message_handler(commands=['quick', 'быстрые'])
    def handle_quick_commands(message: types.Message):
        """Показывает быстрые команды."""
        from commands_list import get_quick_commands
        
        quick_text = get_quick_commands()
        bot.send_message(message.chat.id, quick_text)

    @bot.message_handler(commands=['time', 'время'])
    def handle_time(message: types.Message):
        """Показывает текущее время. Для админов с аргументом — устанавливает тайм-аут."""
        import pytz
        from state import chat_configs
        from config import VOICE_TIMEOUT_MINUTES, CHAT_CONFIG_FILE
        from utils import save_json_data
        
        args = message.text.split()
        
        # Если есть аргумент — это команда установки тайм-аута (только для админов)
        if len(args) > 1:
            if not is_admin(bot, message.from_user.id, message.chat.id):
                return safe_reply(bot, message, "❌ Установка тайм-аута доступна только администраторам.")
            
            chat_id = message.chat.id
            try:
                new_timeout = int(args[1])
                if new_timeout <= 0:
                    raise ValueError("Значение должно быть положительным.")
                
                if str(chat_id) not in chat_configs:
                    chat_configs[str(chat_id)] = {}
                
                chat_configs[str(chat_id)]['voice_timeout'] = new_timeout
                
                if save_json_data(CHAT_CONFIG_FILE, chat_configs):
                    safe_reply(bot, message, f"✅ **Успешно!**\nНапоминания об отсутствии голосовых будут через *{new_timeout} минут* бездействия.")
                    logging.info(f"Администратор {message.from_user.id} изменил тайм-аут для чата {chat_id} на {new_timeout} мин.")
                else:
                    safe_reply(bot, message, "❌ Не удалось сохранить настройку.")
            except (ValueError, IndexError):
                default_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)
                safe_reply(bot, message, f"**Неверный формат.**\n\nИспользуйте: `/time [минуты]`\n*Пример:* `/time 25`\n\nТекущее значение: *{default_timeout} минут*.")
            return
        
        # Без аргументов — показываем время
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.datetime.now(moscow_tz)
        
        time_text = f"🕐 Текущее время: {now.strftime('%H:%M:%S')}\n📅 Дата: {now.strftime('%d.%m.%Y')}\n🌍 Часовой пояс: Москва (MSK)"
        bot.send_message(message.chat.id, time_text)

    @bot.message_handler(commands=['rating', 'рейтинг'])
    def handle_rating(message: types.Message):
        """Показывает рейтинг всех ведущих."""
        from database_manager import db
        
        try:
            rating_data = db.get_user_rating()
            
            if not rating_data:
                bot.send_message(message.chat.id, "📊 Данных для рейтинга пока нет.")
                return
            
            rating_text = ["🏆 РЕЙТИНГ ВЕДУЩИХ 🏆\n"]
            
            for i, (username, total_voices, avg_voices) in enumerate(rating_data[:10], 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                # Экранируем спецсимволы для Markdown
                safe_username = username.replace('_', r'\_').replace('*', r'\*').replace('[', r'\[').replace('`', r'\`')
                rating_text.append(f"{emoji} {safe_username}: {total_voices} голосовых (ср. {avg_voices})")
            
            bot.send_message(message.chat.id, "\n".join(rating_text))
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка получения рейтинга: {e}")

    @bot.message_handler(commands=['status'])
    def handle_status(message: types.Message):
        """Показывает статус системы."""
        from state import chat_data
        import datetime
        
        chat_id = message.chat.id
        
        status_text = ["📊 СТАТУС СИСТЕМЫ\n"]
        
        if chat_id in chat_data and chat_data[chat_id]:
            shift = chat_data[chat_id]
            if shift.users:
                status_text.append("✅ Смена активна")
                status_text.append(f"👥 Участников: {len(shift.users)}")
                
                for user_data in shift.users.values():
                    role = getattr(user_data, 'role', 'караоке_ведущий')
                    from roles import get_role_emoji, get_role_description
                    emoji = get_role_emoji(role)
                    desc = get_role_description(role)
                    safe_username = user_data.username.replace('_', r'\_').replace('*', r'\*').replace('[', r'\[').replace('`', r'\`')
                    
                    status_line = f"  {emoji} {safe_username}: {user_data.count} голосовых ({desc})"
                    
                    # Добавляем статус паузы, если активна
                    if user_data.on_pause:
                        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
                        pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
                        elapsed = (now_moscow - pause_start).total_seconds() / 60
                        remaining = max(0, 40 - elapsed)
                        if remaining > 0:
                            status_line += f" ⏸️ (пауза {int(remaining)} мин)"
                        else:
                            # Пауза истекла, автоматически отключаем
                            user_data.on_pause = False
                            user_data.pause_end_time = now_moscow.isoformat()
                    
                    status_text.append(status_line)
            else:
                status_text.append("⚪ Смена не активна")
        else:
            status_text.append("⚪ Смена не активна")
        
        status_text.append(f"\n🕐 Время: {datetime.datetime.now().strftime('%H:%M:%S')}")
        
        bot.send_message(message.chat.id, "\n".join(status_text))

    @bot.message_handler(commands=['пауза', 'pause'])
    def handle_pause(message: types.Message):
        """Активирует паузу на 40 минут для остановки всех счетчиков."""
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        
        if not shift or not shift.main_id:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_not_started', ["Смена в этом чате еще не началась."]))
            return safe_reply(bot, message, phrase)
            
        # ИСПРАВЛЕНО: Проверяем, что пользователь участник смены (не только main)
        if user_id not in shift.users:
            return safe_reply(bot, message, "Вы не участвуете в текущей смене. Используйте /start для начала.")
            
        user_data = shift.users.get(user_id)
        if not user_data:
            return safe_reply(bot, message, "Не удалось найти ваши данные по текущей смене.")

        # Проверяем, не активна ли уже пауза
        if user_data.on_pause:
            now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
            pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
            elapsed = (now_moscow - pause_start).total_seconds() / 60
            remaining = max(0, 40 - elapsed)
            
            if remaining > 0:
                return safe_reply(bot, message, f"⏸️ Пауза уже активна! Осталось: {int(remaining)} минут.")
            else:
                # Пауза истекла, автоматически отключаем
                user_data.on_pause = False
                user_data.pause_end_time = now_moscow.isoformat()
                safe_reply(bot, message, "⏯️ Предыдущая пауза истекла. Активирую новую паузу на 40 минут...")
        
        # Активируем паузу
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        user_data.on_pause = True
        user_data.pause_start_time = now_moscow.isoformat()
        user_data.pause_end_time = (now_moscow + datetime.timedelta(minutes=40)).isoformat()
        
        # Если пользователь был на перерыве, завершаем перерыв
        if user_data.on_break:
            user_data.on_break = False
            
        # Inline-кнопка для быстрого завершения паузы
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⏯️ Завершить паузу досрочно", callback_data=f"stop_pause_{user_id}"))
        
        safe_reply(bot, message, 
            f"⏸️ **ПАУЗА АКТИВИРОВАНА** на 40 минут!\n\n"
            f"🚫 Все счетчики остановлены\n"
            f"⏰ Пауза до: {(now_moscow + datetime.timedelta(minutes=40)).strftime('%H:%M')}\n"
            f"ℹ️ Для досрочного завершения: `/стоп_пауза`",
            reply_markup=markup)

    @bot.message_handler(commands=['стоп_пауза', 'stop_pause'])
    def handle_stop_pause(message: types.Message):
        """Досрочно завершает активную паузу."""
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        
        if not shift or not shift.main_id:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_not_started', ["Смена в этом чате еще не началась."]))
            return safe_reply(bot, message, phrase)
            
        # ИСПРАВЛЕНО: Проверяем, что пользователь участник смены
        if user_id not in shift.users:
            return safe_reply(bot, message, "Вы не участвуете в текущей смене. Используйте /start для начала.")
            
        user_data = shift.users.get(user_id)
        if not user_data:
            return safe_reply(bot, message, "Не удалось найти ваши данные по текущей смене.")

        # Проверяем, активна ли пауза
        if not user_data.on_pause:
            return safe_reply(bot, message, "❌ Пауза не активна.")
        
        # Завершаем паузу
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
        pause_duration = (now_moscow - pause_start).total_seconds() / 60
        
        user_data.on_pause = False
        user_data.pause_end_time = now_moscow.isoformat()
        
        safe_reply(bot, message, 
            f"⏯️ **ПАУЗА ЗАВЕРШЕНА** досрочно!\n\n"
            f"✅ Все счетчики возобновлены\n"
            f"📊 Длительность паузы: {int(pause_duration)} минут\n"
            f"🎯 Можете продолжать работу!")

    @bot.message_handler(commands=['настройки', 'settings'])
    def handle_chat_settings(message: types.Message):
        """Показывает настройки текущего чата."""
        from state import chat_configs
        import pytz
        
        chat_id = message.chat.id
        config = chat_configs.get(str(chat_id), {})
        
        if not config:
            bot.send_message(chat_id, 
                "⚙️ **НАСТРОЙКИ ЧАТА**\n\n"
                "❌ Настройки для данного чата не найдены.\n"
                "💡 Обратитесь к администратору для настройки чата.")
            return
        
        # Получаем настройки
        brand = config.get('concept', 'Не указан')  # concept вместо brand
        city = config.get('city', 'Не указан') 
        
        # Получаем расписание из schedule объекта
        schedule = config.get('schedule', {})
        start_time = schedule.get('start', 'Не указано')
        end_time = schedule.get('end', 'Не указано')
        
        # Получаем timezone как число и конвертируем в строку часового пояса
        timezone_offset = config.get('timezone', 0)
        
        # Определяем строку часового пояса на основе смещения
        if timezone_offset == 0:
            tz_name = 'Europe/Moscow'
            tz_display = 'Московский (МСК)'
        elif timezone_offset == 2:
            tz_name = 'Asia/Yekaterinburg'
            tz_display = 'Екатеринбургский (МСК+2)'
        elif timezone_offset == 3:
            tz_name = 'Asia/Omsk'
            tz_display = 'Омский (МСК+3)'
        elif timezone_offset == 4:
            tz_name = 'Asia/Krasnoyarsk'
            tz_display = 'Красноярский (МСК+4)'
        elif timezone_offset == 5:
            tz_name = 'Asia/Irkutsk'
            tz_display = 'Иркутский (МСК+5)'
        else:
            tz_name = 'Europe/Moscow'
            tz_display = f'МСК{timezone_offset:+d}'
        
        # Определяем смещение от Москвы
        if timezone_offset == 0:
            offset_text = "Совпадает с Москвой"
        elif timezone_offset > 0:
            offset_text = f"+{timezone_offset} ч от Москвы"
        else:
            offset_text = f"{timezone_offset} ч от Москвы"
        
        # Определяем длительность смены
        try:
            start_hour, start_minute = map(int, start_time.split(':'))
            end_hour, end_minute = map(int, end_time.split(':'))
            
            start_total_minutes = start_hour * 60 + start_minute
            end_total_minutes = end_hour * 60 + end_minute
            
            # Учитываем переход через полночь
            if end_total_minutes < start_total_minutes:
                end_total_minutes += 24 * 60
            
            duration_minutes = end_total_minutes - start_total_minutes
            duration_hours = duration_minutes // 60
            duration_mins = duration_minutes % 60
            
            if duration_mins == 0:
                duration_text = f"{duration_hours} часов"
            else:
                duration_text = f"{duration_hours} ч {duration_mins} мин"
                
        except Exception:
            duration_text = "Не удалось вычислить"
        
        # Формируем красивое сообщение
        settings_text = [
            "⚙️ **НАСТРОЙКИ ЧАТА**\n",
            f"🏢 **Бренд:** {brand}",
            f"🏙️ **Город:** {city}",
            f"🕐 **Время смены:** {start_time} - {end_time}",
            f"⏱️ **Длительность:** {duration_text}",
            f"🌍 **Часовой пояс:** {tz_display}",
            f"🔄 **Относительно Москвы:** {offset_text}",
        ]
        
        # Добавляем текущее время в часовом поясе чата
        try:
            local_tz = pytz.timezone(tz_name)
            current_local = datetime.datetime.now(local_tz)
            settings_text.append(f"\n🕐 **Текущее время здесь:** {current_local.strftime('%H:%M:%S')}")
            settings_text.append(f"📅 **Дата:** {current_local.strftime('%d.%m.%Y')}")
        except Exception:
            pass
            
        bot.send_message(chat_id, "\n".join(settings_text), parse_mode="Markdown")

    @bot.message_handler(commands=['gameover'])
    def handle_gameover(message: types.Message):
        """Завершение смены сотрудником (доступно только после окончания рабочего времени)."""
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        # Проверяем, есть ли активная смена
        shift = chat_data.get(chat_id)
        if not shift or not shift.main_id:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_not_started', ["Смена в этом чате еще не началась."]))
            return safe_reply(bot, message, phrase)
        
        # Проверяем, что команду использует текущий ведущий (любой участник смены)
        if user_id not in shift.users:
            return safe_reply(bot, message, "Вы не участвуете в текущей смене.")
        
        # Проверяем, что рабочее время смены уже закончилось
        from state import chat_configs
        config = chat_configs.get(str(chat_id), {})
        
        # ИСПРАВЛЕНО: timezone хранится как число (offset от Москвы), конвертируем в строку
        timezone_offset = config.get('timezone', 0)
        from config import TIMEZONE_MAP
        # TIMEZONE_MAP использует строковые ключи: "0", "+2", "-1" и т.д.
        tz_key = f"+{timezone_offset}" if timezone_offset > 0 else str(timezone_offset)
        tz_obj = TIMEZONE_MAP.get(tz_key)
        if tz_obj:
            tz_name = str(tz_obj)
        else:
            tz_name = 'Europe/Moscow'
        
        # ИСПРАВЛЕНО: end_time хранится в schedule.end, не в end_time
        schedule = config.get('schedule', {})
        end_time_str = schedule.get('end', config.get('end_time', '04:00'))
        
        try:
            import pytz
            local_tz = pytz.timezone(tz_name)
            now_local = datetime.datetime.now(local_tz)
            
            # Парсим время окончания смены
            end_hour, end_minute = map(int, end_time_str.split(':'))
            end_time = datetime.time(end_hour, end_minute)
            current_time_only = now_local.time()
            
            # Проверяем, что текущее время больше времени окончания смены
            # Учитываем переход через полночь (например, смена до 04:00)
            if end_time.hour < 12:  # Смена заканчивается утром
                shift_ended = (
                    current_time_only >= end_time or 
                    current_time_only >= datetime.time(20, 0)  # Или уже поздний вечер
                )
            else:  # Смена заканчивается вечером
                shift_ended = current_time_only >= end_time
            
            if not shift_ended:
                return safe_reply(bot, message, 
                    f"⏳ **СМЕНА ЕЩЕ НЕ ЗАКОНЧИЛАСЬ**\n\n"
                    f"🕐 Текущее время: {now_local.strftime('%H:%M')}\n"
                    f"⏰ Время окончания смены: {end_time_str}\n"
                    f"🚫 Команда /gameover доступна только после окончания рабочего времени.\n\n"
                    f"💡 Используйте /check для промежуточного отчета.")
            
        except Exception as e:
            logging.error(f"Ошибка при проверке времени смены для /gameover в чате {chat_id}: {e}")
            # Не блокируем — позволяем завершить если ошибка в конфиге
        
        # Если все проверки пройдены — показываем подтверждение
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Да, завершить смену", callback_data="confirm_gameover"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="confirm_gameover_cancel")
        )
        
        user_data = shift.users.get(user_id)
        goal = getattr(user_data, 'goal', shift.shift_goal)
        count = user_data.count if user_data else 0
        pct = (count / goal * 100) if goal > 0 else 0
        
        safe_reply(bot, message, 
            f"🏁 **ЗАВЕРШЕНИЕ СМЕНЫ** 🎭\n\n"
            f"📊 Твой счёт: {count}/{goal} ({pct:.0f}%)\n"
            f"{'🌟 План выполнен! Ты сегодня звезда!' if pct >= 100 else '⚠️ План не дотянул, но бывает...' if pct < 100 else ''}\n"
            f"⚠️ Смена закроется + финальный отчёт.\n\n"
            f"Готов закончить?",
            parse_mode="Markdown", reply_markup=markup)
