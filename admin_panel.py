# admin_panel.py
"""
Модуль для улучшенной админ-панели с кнопками
"""

import logging
from telebot import types
from typing import Optional

from utils import is_admin, get_username
from config import BOSS_ID
from database import db
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
        
        markup.add(types.InlineKeyboardButton("", callback_data="separator"))
        
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
        
        markup.add(types.InlineKeyboardButton("", callback_data="separator"))
        
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
                
            else:
                # Здесь будут другие обработчики
                bot.answer_callback_query(call.id, "🔧 Функция в разработке...")
                
        except Exception as e:
            logging.error(f"Ошибка в админ-панели: {e}")
            bot.answer_callback_query(call.id, "❌ Произошла ошибка", show_alert=True)
