# handlers/user.py

import random
import datetime
import pytz
import logging
import pandas as pd
from collections import Counter
from telebot import types

from utils import get_username, is_admin
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
            return bot.reply_to(message, phrase)
            
        if user_id != shift.main_id:
            main_username = shift.main_username
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('only_for_main_user', ["Эту команду может использовать только текущий главный на смене: {main_username}."]))
            return bot.reply_to(message, phrase.format(main_username=main_username))
            
        main_user_data = shift.users.get(shift.main_id)
        if not main_user_data:
            return bot.reply_to(message, "Не удалось найти ваши данные по текущей смене.")

        shift_goal = shift.shift_goal
        plan_percent = (main_user_data.count / shift_goal * 100) if shift_goal > 0 else 0
        report_lines = [
            f"📋 *Промежуточный отчет для вас* ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
            f"🗣️ **Голосовых:** {main_user_data.count} из {shift_goal} ({plan_percent:.0f}%)",
            f"☕ **Перерывов:** {main_user_data.breaks_count}",
            f"⏳ **Опозданий с перерыва:** {main_user_data.late_returns}"
        ]
        ad_counts = Counter(main_user_data.recognized_ads)
        if ad_counts:
            report_lines.append("\n**📝 Анализ контента:**")
            for ad, count in ad_counts.items():
                report_lines.append(f"✔️ {ad} (x{count})")
        bot.reply_to(message, "\n".join(report_lines), parse_mode="Markdown")

    @bot.message_handler(commands=['сводка'])
    def my_total_stats(message: types.Message):
        if not pd: return bot.reply_to(message, "Модуль для анализа данных (pandas) не загружен.")
        
        user_id = message.from_user.id
        username = get_username(message.from_user)
        bot.reply_to(message, f"📊 Собираю вашу общую статистику из Google Таблицы, {username}. Минутку...")
        
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
                f"⭐️ **Общая статистика для {username}** ⭐️\n\n"
                f"👑 **Всего смен отработано:** {total_shifts}\n"
                f"🗣️ **Всего голосовых записано:** {int(total_voices)}\n"
                f"☕️ **Всего перерывов:** {int(total_breaks)}\n"
                f"⏳ **Всего опозданий с перерыва:** {int(total_lates)}"
            )
            bot.send_message(message.chat.id, report_text, parse_mode="Markdown")
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
    
    @bot.message_handler(commands=['helpadmin', 'админпомощь'])
    def handle_admin_help(message: types.Message):
        """Обработчик команды помощи для админов."""
        from utils import is_admin
        if not is_admin(bot, message.chat.id, message.from_user.id):
            return bot.reply_to(message, "❌ Эта команда доступна только администраторам.")
        
        from help_system import get_admin_help_text
        help_text = get_admin_help_text()
        bot.send_message(message.chat.id, help_text, parse_mode='Markdown')
    
    @bot.message_handler(commands=['роли', 'roles'])
    def handle_roles_info(message: types.Message):
        """Обработчик команды информации о ролях."""
        from help_system import get_roles_help_text
        roles_text = get_roles_help_text()
        bot.send_message(message.chat.id, roles_text, parse_mode='Markdown')
