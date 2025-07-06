# handlers/shift.py

import random
import datetime
import pytz
import threading

from telebot import types

from utils import get_username, init_shift_data, init_user_data, handle_user_return, save_history_event
from state import chat_data, pending_transfers
from config import BREAK_KEYWORDS, RETURN_CONFIRM_WORDS, BREAK_DELAY_MINUTES, BREAK_DURATION_MINUTES
from phrases import soviet_phrases

def register_shift_handlers(bot):

    @bot.message_handler(commands=['start', 'старт'])
    def handle_start(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: 
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('group_only_command', ["Эта команда работает только в групповом чате."]))
            return bot.reply_to(message, phrase)
            
        from_user = message.from_user
        username = get_username(from_user)
        
        if chat_id not in chat_data or not chat_data[chat_id]: 
            init_shift_data(chat_id)
        
        shift = chat_data[chat_id]
        if from_user.id not in shift.users:
            shift.users[from_user.id] = init_user_data(from_user.id, username)
            
        if shift.main_id is not None:
            main_username = shift.main_username
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('start_shift_fail_taken', ["Смена уже занята. Текущий главный: {main_username}."]))
            return bot.reply_to(message, phrase.format(main_username=main_username))
            
        shift.main_id = from_user.id
        shift.main_username = username
        
        phrase = random.choice(soviet_phrases.get("system_messages", {}).get('start_shift_success', ["👑 {username}, вы заступили на смену! Удачи!"]))
        bot.send_message(chat_id, phrase.format(username=username))
        save_history_event(chat_id, from_user.id, username, "Стал главным на смене (команда /start)")

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
