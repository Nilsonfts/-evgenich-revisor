# handlers/shift.py

import random
import datetime
import pytz
import threading
import logging

from telebot import types

from utils import get_username, init_shift_data, init_user_data, handle_user_return, save_history_event
from state import chat_data, pending_transfers
from config import BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, BREAK_DELAY_MINUTES, BREAK_DURATION_MINUTES
from phrases import soviet_phrases
from roles import (
    get_current_day_type, get_roles_for_day_type, get_goals_for_day_type,
    UserRole, ROLE_EMOJIS, ROLE_DESCRIPTIONS, is_weekend_shift
)
from database import db

def register_shift_handlers(bot):

    @bot.message_handler(commands=['start', 'старт'])
    def handle_start(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: 
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('group_only_command', ["Эта команда работает только в групповом чате."]))
            return bot.reply_to(message, phrase)
            
        from_user = message.from_user
        username = get_username(from_user)
        
        # Парсим роль из аргументов команды
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []
        requested_role = None
        
        if args:
            role_arg = " ".join(args).lower()
            if "караоке" in role_arg or "karaoke" in role_arg:
                requested_role = UserRole.KARAOKE_HOST.value
            elif "мс" in role_arg or "mc" in role_arg:
                requested_role = UserRole.MC.value
        
        # Определяем доступные роли для текущего дня
        current_day_type = get_current_day_type()
        available_roles = get_roles_for_day_type(current_day_type)
        role_goals = get_goals_for_day_type(current_day_type)
        
        # Проверяем запрошенную роль
        if requested_role and requested_role not in available_roles:
            available_list = ", ".join([f"{ROLE_EMOJIS[r]} {ROLE_DESCRIPTIONS[r]}" for r in available_roles])
            return bot.reply_to(message, 
                f"❌ Роль '{ROLE_DESCRIPTIONS.get(requested_role, requested_role)}' недоступна сегодня.\n"
                f"📅 Доступные роли для {current_day_type.value} дня: {available_list}")
        
        # Инициализируем данные смены если их нет
        if chat_id not in chat_data or not chat_data[chat_id]: 
            init_shift_data(chat_id)
        
        shift = chat_data[chat_id]
        
        # 🚀 АВТОМАТИЧЕСКАЯ ПОДДЕРЖКА ДЛЯ ПТ-СБ - ДОБАВЛЯЕМ ВТОРОГО ВЕДУЩЕГО
        # Проверяем, может ли пользователь присоединиться к активной смене в выходные
        if shift.users and from_user.id not in shift.users:
            # В выходные дни (ПТ-СБ) автоматически разрешаем второго ведущего
            if is_weekend_shift() and len(shift.users) < 2:
                # Проверяем, какие роли уже заняты
                occupied_roles = set()
                for user_data in shift.users.values():
                    if hasattr(user_data, 'role'):
                        occupied_roles.add(user_data.role)
                
                # Ищем свободную роль
                available_for_join = [role for role in available_roles if role not in occupied_roles]
                
                if available_for_join:
                    # Автоматически назначаем свободную роль
                    auto_assigned_role = requested_role if requested_role in available_for_join else available_for_join[0]
                    
                    # Создаем пользователя с назначенной ролью
                    shift.users[from_user.id] = init_user_data(from_user.id, username, auto_assigned_role)
                    
                    # Устанавливаем цель для роли
                    user_goal = role_goals.get(auto_assigned_role, 15)
                    shift.users[from_user.id].goal = user_goal
                    
                    role_emoji = ROLE_EMOJIS.get(auto_assigned_role, "👤")
                    role_desc = ROLE_DESCRIPTIONS.get(auto_assigned_role, auto_assigned_role)
                    
                    weekend_success_text = [
                        f"🎉 **ВЫХОДНОЙ ДЕНЬ - ДОБАВЛЕН ВТОРОЙ ВЕДУЩИЙ!**",
                        f"",
                        f"{role_emoji} {username} присоединился как **{role_desc}**",
                        f"🎯 Ваша цель: {user_goal} голосовых сообщений",
                        f"",
                        f"💫 Теперь работают 2 ведущих параллельно!",
                        f"📊 Используйте /check для проверки прогресса"
                    ]
                    
                    bot.send_message(chat_id, "\n".join(weekend_success_text))
                    save_history_event(chat_id, from_user.id, username, f"Присоединился к смене в выходной как {role_desc}")
                    
                    # Сохраняем в БД
                    try:
                        db.save_shift_data(chat_id, shift)
                    except Exception as e:
                        logging.error(f"Ошибка сохранения данных в БД: {e}")
                    
                    return
            
            # Если не можем присоединиться, показываем ошибку
            if shift.users:
                main_user = shift.main_username or "неизвестный"
                occupied_list = ", ".join([f"{ROLE_EMOJIS.get(getattr(u, 'role', 'караоке_ведущий'), '👤')} {getattr(u, 'username', 'Неизвестный')}" 
                                         for u in shift.users.values()])
                return bot.reply_to(message, 
                    f"⚠️ Смена уже идет!\n"
                    f"🎭 Занятые роли: {occupied_list}\n"
                    f"{'💡 В выходные можно добавить второго ведущего!' if is_weekend_shift() and len(shift.users) < 2 else 'Дождитесь окончания смены или используйте /передать'}")

        # Определяем роль для назначения
        if requested_role:
            assigned_role = requested_role
        else:
            # Автоматическое назначение роли
            # Сначала проверяем, какие роли уже заняты
            occupied_roles = set()
            for user_data in shift.users.values():
                if hasattr(user_data, 'role'):
                    occupied_roles.add(user_data.role)
            
            # Назначаем первую свободную роль
            assigned_role = None
            for role in available_roles:
                if role not in occupied_roles:
                    assigned_role = role
                    break
            
            if not assigned_role:
                occupied_list = ", ".join([f"{ROLE_EMOJIS[r]} {ROLE_DESCRIPTIONS[r]}" for r in occupied_roles])
                return bot.reply_to(message, 
                    f"❌ Все роли уже заняты.\n"
                    f"🎭 Занятые роли: {occupied_list}")
        
        # Проверяем, не занята ли уже эта роль
        for user_data in shift.users.values():
            if hasattr(user_data, 'role') and user_data.role == assigned_role:
                role_emoji = ROLE_EMOJIS.get(assigned_role, "👤")
                role_desc = ROLE_DESCRIPTIONS.get(assigned_role, assigned_role)
                return bot.reply_to(message, 
                    f"❌ Роль {role_emoji} {role_desc} уже занята пользователем {user_data.username}")
        
        # Создаем или обновляем данные пользователя с ролью
        if from_user.id not in shift.users:
            shift.users[from_user.id] = init_user_data(from_user.id, username, assigned_role)
        else:
            shift.users[from_user.id].role = assigned_role
        
        # Обновляем конфигурацию смены
        if not hasattr(shift, 'active_roles'):
            shift.active_roles = available_roles
        if not hasattr(shift, 'role_goals'):
            shift.role_goals = role_goals
        
        # Устанавливаем цель для пользователя
        user_goal = role_goals.get(assigned_role, 15)
        shift.users[from_user.id].goal = user_goal
        
        # Для совместимости оставляем main_id (будет первый заступивший)
        if shift.main_id is None:
            shift.main_id = from_user.id
            shift.main_username = username
        
        role_emoji = ROLE_EMOJIS.get(assigned_role, "👤")
        role_desc = ROLE_DESCRIPTIONS.get(assigned_role, assigned_role)
        
        success_text = [
            f"🎉 {username}, вы заступили на смену!",
            f"🎭 Роль: {role_emoji} {role_desc}",
            f"🎯 Цель: {user_goal} голосовых сообщений",
            f"📅 Тип дня: {current_day_type.value}"
        ]
        
        bot.send_message(chat_id, "\n".join(success_text))
        save_history_event(chat_id, from_user.id, username, f"Заступил на смену с ролью {role_desc}")
        
        # Сохраняем в базу данных
        try:
            db.save_shift_data(chat_id, shift)
        except Exception as e:
            logging.error(f"Ошибка сохранения смены в БД: {e}")

    @bot.message_handler(func=lambda m: m.text and any(word in m.text.lower().split() for word in BREAK_KEYWORDS))
    def handle_break_request(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        if not shift or shift.main_id != user_id: return
        
        user_data = shift.users.get(user_id)
        if not user_data: return
        
        if user_data.on_break:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('break_already_on', ["Вы уже на перерыве."]))
            return bot.reply_to(message, phrase)
            
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        
        if user_data.last_break_time:
            last_break_time = datetime.datetime.fromisoformat(user_data.last_break_time)
            if (now_moscow - last_break_time).total_seconds() / 60 < BREAK_DELAY_MINUTES:
                remaining_time = int(BREAK_DELAY_MINUTES - (now_moscow - last_break_time).total_seconds() / 60)
                phrase = random.choice(soviet_phrases.get("system_messages", {}).get('break_cooldown', ["Следующий перерыв можно взять через {remaining_time} мин."]))
                return bot.reply_to(message, phrase.format(remaining_time=remaining_time))
            
        user_data.on_break = True
        user_data.break_start_time = now_moscow.isoformat()
        user_data.last_break_time = now_moscow.isoformat()
        user_data.breaks_count += 1
        user_data.last_break_reminder_time = None
        
        response_phrase = random.choice(soviet_phrases.get('break_acknowledgement', ['Перерыв начат.']))
        bot.reply_to(message, f"{response_phrase} на {BREAK_DURATION_MINUTES} минут.")

    @bot.message_handler(func=lambda m: m.text and any(word in m.text.lower().split() for word in RETURN_CONFIRM_WORDS))
    def handle_return_message(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        if not shift or shift.main_id != user_id: return
        
        handle_user_return(bot, chat_id, user_id)

    def cancel_transfer(chat_id: int):
        """Отменяет предложение о передаче смены по таймауту."""
        if chat_id in pending_transfers:
            transfer_info = pending_transfers.pop(chat_id)
            try:
                bot.edit_message_reply_markup(chat_id, transfer_info['message_id'], reply_markup=None)
                phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_transfer_timeout', ["Время на принятие смены вышло. Предложение аннулировано."]))
                bot.send_message(chat_id, phrase.format(
                    from_username=transfer_info['from_username'],
                    to_username=transfer_info['to_username']
                ))
            except Exception as e:
                logging.warning(f"Не удалось отменить передачу смены (сообщение могло быть удалено): {e}")

    @bot.message_handler(commands=['передать'])
    def handle_shift_transfer_request(message: types.Message):
        chat_id = message.chat.id
        from_user = message.from_user
        shift = chat_data.get(chat_id)
        
        if not shift or shift.main_id != from_user.id:
            return bot.reply_to(message, "Только текущий главный на смене может передать ее.")

        if not message.reply_to_message:
            return bot.reply_to(message, "Чтобы передать смену, ответьте этой командой на любое сообщение пользователя, которому вы хотите ее передать.")

        to_user = message.reply_to_message.from_user
        if to_user.is_bot: return bot.reply_to(message, "Нельзя передать смену боту.")
        if to_user.id == from_user.id: return bot.reply_to(message, "Нельзя передать смену самому себе.")
        if chat_id in pending_transfers: return bot.reply_to(message, "В данный момент уже есть активное предложение о передаче смены. Дождитесь его завершения.")

        from_username = get_username(from_user)
        to_username = get_username(to_user)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять смену", callback_data=f"transfer_accept_{to_user.id}"))
        
        phrase_template = random.choice(soviet_phrases.get("system_messages", {}).get('shift_transfer_offer', ["{from_username} предлагает передать смену {to_username}."]))
        text = phrase_template.format(from_username=from_username, to_username=to_username)
        
        sent_message = bot.send_message(chat_id, text, reply_markup=markup)
        
        timer = threading.Timer(300, cancel_transfer, args=[bot, chat_id])
        timer.start()
        
        pending_transfers[chat_id] = {
            'from_id': from_user.id, 'from_username': from_username,
            'to_id': to_user.id, 'to_username': to_username,
            'message_id': sent_message.message_id, 'timer': timer
        }
