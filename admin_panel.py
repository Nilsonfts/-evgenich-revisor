# admin_panel.py
"""
Модуль для улучшенной админ-панели с кнопками
"""

import logging
from telebot import types
from typing import Optional

from utils import is_admin, get_username
from config import BOSS_ID
from database_manager import db  # Единый database manager
from roles import (
    get_current_day_type, get_roles_for_day_type, get_goals_for_day_type,
    DayType, UserRole, ROLE_EMOJIS, ROLE_DESCRIPTIONS, DAY_TYPE_MAPPING
)

class AdminPanel:
    """Класс для управления админ-панелью"""
    
    @staticmethod
    def create_main_menu(user_id: int, chat_id: int) -> types.InlineKeyboardMarkup:
        """Создает главное меню админ-панели"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Основные функции
        markup.add(
            types.InlineKeyboardButton("📊 Статус смены", callback_data="admin_status"),
            types.InlineKeyboardButton("📈 Рейтинг", callback_data="admin_rating")
        )
        
        markup.add(
            types.InlineKeyboardButton("🎭 Управление ролями", callback_data="admin_roles"),
            types.InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")
        )
        
        markup.add(
            types.InlineKeyboardButton("🔄 Перезапуск смены", callback_data="admin_restart"),
            types.InlineKeyboardButton("📝 Досрочный отчет", callback_data="admin_report")
        )
        
        markup.add(
            types.InlineKeyboardButton("🚨 Проблемы", callback_data="admin_problems"),
            types.InlineKeyboardButton("📜 Лог смены", callback_data="admin_log")
        )
        
        # Управление ботом
        bot_status = "🟢" if db.is_bot_enabled(chat_id) else "🔴"
        markup.add(
            types.InlineKeyboardButton(f"{bot_status} Бот вкл/выкл", callback_data="admin_toggle_bot")
        )
        
        # Функции только для BOSS
        if user_id == BOSS_ID:
            markup.add(
                types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")
            )
        
        markup.add(
            types.InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")
        )
        
        return markup
    
    @staticmethod
    def create_roles_menu(chat_id: int) -> types.InlineKeyboardMarkup:
        """Создает меню управления ролями"""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        current_day_type = get_current_day_type()
        current_roles = get_roles_for_day_type(current_day_type)
        
        markup.add(
            types.InlineKeyboardButton(
                f"📅 Сегодня: {current_day_type.value} день", 
                callback_data="admin_day_info"
            )
        )
        
        markup.add(types.InlineKeyboardButton("─────────────", callback_data="separator"))
        
        # Показываем активные роли
        for role in current_roles:
            emoji = ROLE_EMOJIS.get(role, "👤")
            description = ROLE_DESCRIPTIONS.get(role, role)
            markup.add(
                types.InlineKeyboardButton(
                    f"{emoji} {description}", 
                    callback_data=f"admin_role_info_{role}"
                )
            )
        
        markup.add(types.InlineKeyboardButton("─────────────", callback_data="separator"))
        
        # Управление
        markup.add(
            types.InlineKeyboardButton("⚙️ Настроить расписание", callback_data="admin_schedule_config"),
            types.InlineKeyboardButton("📊 Статистика по ролям", callback_data="admin_roles_stats")
        )
        
        markup.add(
            types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )
        
        return markup
    
    @staticmethod
    def create_schedule_config_menu() -> types.InlineKeyboardMarkup:
        """Создает меню конфигурации расписания"""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        markup.add(
            types.InlineKeyboardButton("📅 Будние дни (вс-чт)", callback_data="admin_config_weekday"),
            types.InlineKeyboardButton("🎉 Выходные дни (пт-сб)", callback_data="admin_config_weekend")
        )
        
        markup.add(
            types.InlineKeyboardButton("🔙 Назад к ролям", callback_data="admin_roles")
        )
        
        return markup
    
    @staticmethod
    def create_day_config_menu(day_type: DayType) -> types.InlineKeyboardMarkup:
        """Создает меню конфигурации для типа дня"""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        current_roles = get_roles_for_day_type(day_type)
        
        markup.add(
            types.InlineKeyboardButton(
                f"Настройка: {day_type.value} день", 
                callback_data="separator"
            )
        )
        
        # Переключатели ролей
        for role_enum in UserRole:
            role = role_enum.value
            emoji = ROLE_EMOJIS.get(role, "👤")
            status = "✅" if role in current_roles else "❌"
            markup.add(
                types.InlineKeyboardButton(
                    f"{status} {emoji} {ROLE_DESCRIPTIONS[role]}", 
                    callback_data=f"admin_toggle_role_{day_type.value}_{role}"
                )
            )
        
        markup.add(
            types.InlineKeyboardButton("💾 Сохранить", callback_data=f"admin_save_config_{day_type.value}"),
            types.InlineKeyboardButton("🔙 Назад", callback_data="admin_schedule_config")
        )
        
        return markup
    
    @staticmethod
    def create_bot_control_menu(chat_id: int) -> types.InlineKeyboardMarkup:
        """Создает меню управления ботом"""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        is_enabled = db.is_bot_enabled(chat_id)
        
        if is_enabled:
            markup.add(
                types.InlineKeyboardButton("🔴 Выключить бота", callback_data="admin_bot_disable")
            )
        else:
            markup.add(
                types.InlineKeyboardButton("🟢 Включить бота", callback_data="admin_bot_enable")
            )
        
        markup.add(
            types.InlineKeyboardButton("🔙 Назад в меню", callback_data="admin_main")
        )
        
        return markup

def register_admin_panel_handlers(bot):
    """Регистрирует обработчики для админ-панели"""
    
    @bot.message_handler(commands=['admin'])
    def handle_admin_command(message: types.Message):
        """Обработчик команды /admin"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Проверяем права доступа
        if not is_admin(bot, user_id, chat_id):
            bot.reply_to(message, "❌ У вас нет прав администратора для использования этой команды.")
            return
        
        username = get_username(message.from_user)
        
        # Создаем главное меню
        markup = AdminPanel.create_main_menu(user_id, chat_id)
        
        admin_text = [
            "⚜️ **ПАНЕЛЬ АДМИНИСТРАТОРА** ⚜️",
            f"👤 Администратор: {username}",
            f"🏠 Чат ID: {chat_id}",
            "",
            "Выберите действие:"
        ]
        
        bot.send_message(
            chat_id, 
            "\n".join(admin_text), 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
    def handle_admin_callbacks(call: types.CallbackQuery):
        """Обработчик колбэков админ-панели"""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        
        # Проверяем права доступа
        if not is_admin(bot, user_id, chat_id):
            bot.answer_callback_query(call.id, "❌ Нет прав доступа", show_alert=True)
            return
        
        try:
            if call.data == "admin_main":
                markup = AdminPanel.create_main_menu(user_id, chat_id)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_roles":
                markup = AdminPanel.create_roles_menu(chat_id)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_schedule_config":
                markup = AdminPanel.create_schedule_config_menu()
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_config_weekday":
                markup = AdminPanel.create_day_config_menu(DayType.WEEKDAY)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_config_weekend":
                markup = AdminPanel.create_day_config_menu(DayType.WEEKEND)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_toggle_bot":
                markup = AdminPanel.create_bot_control_menu(chat_id)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_bot_enable":
                admin_username = get_username(call.from_user)
                db.set_bot_enabled(chat_id, True, user_id)
                bot.answer_callback_query(call.id, "🟢 Бот включен!")
                markup = AdminPanel.create_main_menu(user_id, chat_id)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_bot_disable":
                admin_username = get_username(call.from_user)
                db.set_bot_enabled(chat_id, False, user_id)
                bot.answer_callback_query(call.id, "🔴 Бот выключен!")
                markup = AdminPanel.create_main_menu(user_id, chat_id)
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
                
            elif call.data == "admin_close":
                bot.delete_message(chat_id, call.message.message_id)
                bot.answer_callback_query(call.id, "Панель закрыта")
                
            elif call.data == "separator":
                bot.answer_callback_query(call.id)  # Игнорируем нажатия на разделители
                
            elif call.data == "admin_status":
                # Показываем статус смены
                from state import chat_data
                from utils import generate_detailed_report
                shift = chat_data.get(chat_id)
                if not shift or not shift.main_id:
                    bot.answer_callback_query(call.id, "Смена не активна")
                    bot.send_message(chat_id, "⚪ Смена в этом чате еще не началась.")
                else:
                    report_lines = generate_detailed_report(chat_id, shift)
                    report_text = "\n".join(report_lines)
                    bot.send_message(chat_id, report_text, parse_mode="Markdown")
                    bot.answer_callback_query(call.id, "📊 Статус смены")
                    
            elif call.data == "admin_report":
                # Досрочный отчет с подтверждением
                from telebot import types as t
                markup = t.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    t.InlineKeyboardButton("✅ Да, завершить", callback_data="confirm_report"),
                    t.InlineKeyboardButton("❌ Отмена", callback_data="confirm_report_cancel")
                )
                bot.send_message(chat_id,
                    "📝 **Досрочный отчёт**\n\n"
                    "⚠️ Это завершит текущую смену.\nВы уверены?",
                    parse_mode="Markdown", reply_markup=markup)
                bot.answer_callback_query(call.id, "📝 Подтвердите действие")
                    
            elif call.data == "admin_problems":
                # Анализ проблемных зон
                bot.answer_callback_query(call.id, "🚨 Анализирую...")
                try:
                    import pandas as pd
                    from g_sheets import get_sheet
                    from config import VOICE_TIMEOUT_MINUTES
                    from state import chat_configs
                    worksheet = get_sheet()
                    if not worksheet:
                        bot.send_message(chat_id, "Не удалось подключиться к Google Таблице.")
                    else:
                        df = pd.DataFrame(worksheet.get_all_records())
                        if df.empty:
                            bot.send_message(chat_id, "В таблице нет данных.")
                        else:
                            chat_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)
                            numeric_cols = ['Выполнение (%)', 'Опозданий (шт)', 'Макс. пауза (мин)']
                            for col in numeric_cols:
                                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                            df.dropna(subset=numeric_cols, inplace=True)
                            low_perf = df[df['Выполнение (%)'] < 80]
                            report_lines = ["🚨 **Анализ проблемных зон**\n"]
                            if not low_perf.empty:
                                report_lines.append("*📉 Низкое выполнение плана (<80%):*")
                                for _, row in low_perf.head(5).iterrows():
                                    report_lines.append(f" - {row.get('Дата', 'N/A')} {row.get('Тег Ведущего', 'N/A')}: *{row['Выполнение (%)']:.0f}%*")
                            if len(report_lines) == 1:
                                bot.send_message(chat_id, "✅ Проблемных зон не найдено!")
                            else:
                                bot.send_message(chat_id, "\n".join(report_lines), parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Ошибка анализа проблем в админ-панели: {e}")
                    bot.send_message(chat_id, f"❌ Ошибка: {e}")
            
            elif call.data == "admin_rating":
                bot.answer_callback_query(call.id, "📈 Загружаю рейтинг...")
                try:
                    from database_manager import db as db_inst
                    rating_data = db_inst.get_user_rating()
                    if not rating_data:
                        bot.send_message(chat_id, "📊 Данных для рейтинга пока нет.")
                    else:
                        rating_text = ["🏆 **РЕЙТИНГ ВЕДУЩИХ** 🏆\n"]
                        for i, (username, total_voices, avg_voices) in enumerate(rating_data[:10], 1):
                            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                            safe_username = username.replace('_', r'\_').replace('*', r'\*')
                            rating_text.append(f"{emoji} {safe_username}: {total_voices} ГС (ср. {avg_voices})")
                        bot.send_message(chat_id, "\n".join(rating_text), parse_mode="Markdown")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ Ошибка получения рейтинга: {e}")
            
            elif call.data == "admin_restart":
                # Подтверждение сброса смены
                from telebot import types as t
                markup = t.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    t.InlineKeyboardButton("✅ Да, сбросить", callback_data="confirm_restart"),
                    t.InlineKeyboardButton("❌ Отмена", callback_data="confirm_restart_cancel")
                )
                bot.send_message(chat_id,
                    "🔄 **Сброс смены**\n\n"
                    "⚠️ Это необратимое действие! Все данные текущей смены будут потеряны.\n"
                    "Вы уверены?",
                    parse_mode="Markdown", reply_markup=markup)
                bot.answer_callback_query(call.id, "🔄 Подтвердите действие")
            
            elif call.data == "admin_log":
                bot.answer_callback_query(call.id, "📜 Формирую лог...")
                import datetime as dt
                from state import user_history
                history = user_history.get(chat_id)
                if not history:
                    bot.send_message(chat_id, "История событий пуста.")
                else:
                    try:
                        filename = f"history_{chat_id}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                        import os
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(f"История событий для чата\n" + "="*40 + "\n")
                            for event in history:
                                if isinstance(event, dict):
                                    ts = event.get('timestamp', '')
                                    user = event.get('username', '')
                                    desc = event.get('event', '')
                                    f.write(f"[{ts}] {user}: {desc}\n")
                                else:
                                    f.write(f"{event}\n")
                        with open(filename, 'rb') as f_rb:
                            bot.send_document(chat_id, f_rb, caption="📜 Лог событий текущей смены.")
                        os.remove(filename)
                    except Exception as e:
                        bot.send_message(chat_id, f"❌ Ошибка: {e}")
            
            elif call.data == "admin_broadcast":
                if user_id != BOSS_ID:
                    bot.answer_callback_query(call.id, "⛔️ Только для BOSS", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, "📢 Рассылка")
                    bot.send_message(chat_id, "📢 Для рассылки используйте команду `/broadcast [текст]`", parse_mode="Markdown")
            
            elif call.data == "admin_roles_stats":
                bot.answer_callback_query(call.id, "📊 Статистика")
                from state import chat_data
                shift = chat_data.get(chat_id)
                if not shift or not shift.users:
                    bot.send_message(chat_id, "⚪ Нет активной смены для статистики.")
                else:
                    from roles import get_role_emoji, get_role_description
                    lines = ["📊 **Статистика по ролям**\n"]
                    for uid, ud in shift.users.items():
                        role = getattr(ud, 'role', 'караоке_ведущий')
                        emoji = get_role_emoji(role)
                        desc = get_role_description(role)
                        goal = getattr(ud, 'goal', shift.shift_goal)
                        pct = (ud.count / goal * 100) if goal > 0 else 0
                        lines.append(f"{emoji} {ud.username}: {ud.count}/{goal} ({pct:.0f}%) — {desc}")
                    bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
            
            else:
                bot.answer_callback_query(call.id, "🔧 Функция в разработке...")
                
        except Exception as e:
            logging.error(f"Ошибка в админ-панели: {e}")
            bot.answer_callback_query(call.id, "❌ Произошла ошибка", show_alert=True)
