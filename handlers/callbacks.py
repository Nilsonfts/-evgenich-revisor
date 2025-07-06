# handlers/callbacks.py

import logging
from telebot import types

from utils import is_admin, get_username, init_user_data, save_json_data
from state import chat_data, pending_transfers, ad_templates, user_states
from phrases import soviet_phrases
from config import AD_TEMPLATES_FILE

def register_callback_handlers(bot):

    # Этот хендлер должен быть здесь, т.к. он связан с кнопкой, создаваемой в shift.py
    @bot.callback_query_handler(func=lambda call: call.data.startswith('transfer_accept_'))
    def handle_shift_transfer_accept(call: types.CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        if chat_id not in pending_transfers:
            return bot.answer_callback_query(call.id, "Предложение о передаче смены уже неактуально.", show_alert=True)
        
        transfer_info = pending_transfers[chat_id]
        
        if user_id != transfer_info['to_id']:
            return bot.answer_callback_query(call.id, "Это предложение адресовано не вам.", show_alert=True)
            
        transfer_info['timer'].cancel()
        
        shift = chat_data.get(chat_id)
        if not shift:
             bot.answer_callback_query(call.id, "Ошибка: данные смены не найдены.", show_alert=True)
             return

        shift.main_id = transfer_info['to_id']
        shift.main_username = transfer_info['to_username']
        
        if transfer_info['to_id'] not in shift.users:
            shift.users[transfer_info['to_id']] = init_user_data(transfer_info['to_id'], transfer_info['to_username'])

        del pending_transfers[chat_id]
        
        bot.answer_callback_query(call.id, "Смена принята!")
        try: bot.delete_message(chat_id, call.message.message_id)
        except Exception: pass
        
        phrase_template = random.choice(soviet_phrases.get("system_messages", {}).get('shift_transfer_success', ["."]))
        text = phrase_template.format(from_username=transfer_info['from_username'], to_username=transfer_info['to_username'])
        bot.send_message(chat_id, text)
        save_history_event(chat_id, user_id, transfer_info['to_username'], f"Принял смену от {transfer_info['from_username']}")

    # Этот хендлер обрабатывает кнопки, связанные с меню /ads из wizards.py
    @bot.callback_query_handler(func=lambda call: call.data.startswith('ad_'))
    def handle_ad_callbacks(call: types.CallbackQuery):
        if not is_admin(bot, call.from_user.id, call.message.chat.id):
            return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
        
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        bot.answer_callback_query(call.id)
        parts = call.data.split('_')
        action = parts[1]

        try: 
            bot.delete_message(chat_id, message_id)
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}")

        # Импортируем локально, чтобы избежать циклических зависимостей
        from .wizards import show_ad_cities_menu, show_ad_actions_menu, show_templates_for_deletion, command_ads

        if action == "brand":
            brand = parts[2]
            show_ad_cities_menu(bot, chat_id, brand)
        elif action == "city":
            brand, city = parts[2], parts[3]
            show_ad_actions_menu(bot, chat_id, brand, city)
        elif action == "view":
            brand, city = parts[2], parts[3]
            templates = ad_templates.get(brand, {}).get(city, {})
            if not templates: text = "Шаблонов для этого города пока нет."
            else:
                text_lines = [f"📄 **Шаблоны для {brand.upper()} / {city.capitalize()}**\n"]
                for name, content in templates.items():
                    text_lines.append(f"🔹 *{name}*:\n`{content}`\n")
                text = "\n".join(text_lines)
            bot.send_message(chat_id, text, parse_mode="Markdown")
        elif action == "addform":
            brand, city = parts[2], parts[3]
            user_id = call.from_user.id
            user_states[user_id] = {"state": "awaiting_ad_template", "brand": brand, "city": city}
            bot.send_message(chat_id, "Отправьте сообщение в формате:\n\n`Название шаблона`\n`Текст шаблона...`\n\nДля отмены введите /cancel", parse_mode="Markdown")
        elif action == "delform":
            brand, city = parts[2], parts[3]
            show_templates_for_deletion(bot, chat_id, brand, city)
        elif action == "delete":
            brand, city, tpl_key = parts[2], parts[3], "_".join(parts[4:])
            if tpl_key in ad_templates.get(brand, {}).get(city, {}):
                del ad_templates[brand][city][tpl_key]
                if save_json_data(AD_TEMPLATES_FILE, ad_templates):
                     bot.send_message(chat_id, f"Шаблон '{tpl_key}' удален.")
                     # После удаления снова показываем список для удаления
                     show_templates_for_deletion(bot, chat_id, brand, city)
                else:
                    bot.send_message(chat_id, "Ошибка сохранения!")
        elif action == 'backtobrand':
            command_ads(call.message)
        elif action == 'backtocity':
            brand = parts[2]
            show_ad_cities_menu(bot, chat_id, brand)

    @bot.callback_query_handler(func=lambda call: True)
    def _debug_all_callbacks(call: types.CallbackQuery):
        """Перехватывает все необработанные колбэки для отладки."""
        try:
            bot.answer_callback_query(call.id, f"Необработанный колбэк: {call.data}", show_alert=False)
        except Exception:
            pass
        logging.warning(f"Получен необработанный callback_data -> {call.data} от {get_username(call.from_user)} в чате {call.message.chat.id}")
