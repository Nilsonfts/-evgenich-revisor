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

    # Полностью новые обработчики для системы рекламы /ads
    @bot.callback_query_handler(func=lambda call: call.data.startswith('ads_'))
    def handle_ads_callbacks(call: types.CallbackQuery):
        """Обработчик для системы рекламных шаблонов."""
        if not is_admin(bot, call.from_user.id, call.message.chat.id):
            return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
        
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        action = call.data[4:]  # убираем "ads_"
        
        import json
        try:
            with open('ad_templates.json', 'r', encoding='utf-8') as f:
                ad_templates = json.load(f)
        except FileNotFoundError:
            bot.send_message(chat_id, "❌ Файл рекламных шаблонов не найден!")
            return
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка загрузки файла: {e}")
            return
        
        try:
            # Удаляем старое сообщение
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        
        if action == "view_all":
            # КНОПКА: "📋 Просмотр шаблонов"
            text_lines = ["📋 ВСЕ РЕКЛАМНЫЕ ШАБЛОНЫ\n"]
            template_count = 0
            
            for brand, cities in ad_templates.items():
                text_lines.append(f"🏢 {brand.upper()}")
                for city, templates in cities.items():
                    text_lines.append(f"   📍 {city.capitalize()}: {len(templates)} шаблонов")
                    for i, (name, content) in enumerate(templates.items(), 1):
                        template_count += 1
                        preview = content[:80] + "..." if len(content) > 80 else content
                        text_lines.append(f"      {i}. {name}")
                        text_lines.append(f"         {preview}")
                text_lines.append("")
            
            text = "\n".join(text_lines) if template_count > 0 else "📝 Рекламных шаблонов пока нет"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_back_main"))
            bot.send_message(chat_id, text, reply_markup=markup)
            
        elif action == "by_brands":
            # КНОПКА: "🏢 По брендам"  
            markup = types.InlineKeyboardMarkup()
            
            for brand in ad_templates.keys():
                total_templates = sum(len(city_data) for city_data in ad_templates[brand].values())
                btn = types.InlineKeyboardButton(
                    f"🏢 {brand.upper()} ({total_templates})", 
                    callback_data=f"ads_brand_{brand}"
                )
                markup.add(btn)
            
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_back_main"))
            bot.send_message(chat_id, "🏢 Выберите бренд для просмотра:", reply_markup=markup)
            
        elif action.startswith("brand_"):
            # Показать города для бренда
            brand = action[6:]  # убираем "brand_"
            cities = ad_templates.get(brand, {})
            
            if not cities:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("« К брендам", callback_data="ads_by_brands"))
                bot.send_message(chat_id, f"📍 У бренда {brand.upper()} пока нет городов", reply_markup=markup)
                return
                
            markup = types.InlineKeyboardMarkup()
            for city, templates in cities.items():
                btn = types.InlineKeyboardButton(
                    f"📍 {city.capitalize()} ({len(templates)})", 
                    callback_data=f"ads_city_{brand}_{city}"
                )
                markup.add(btn)
            
            markup.add(types.InlineKeyboardButton("« К брендам", callback_data="ads_by_brands"))
            bot.send_message(chat_id, f"📍 Города для {brand.upper()}:", reply_markup=markup)
            
        elif action.startswith("city_"):
            # Показать шаблоны для конкретного города
            parts = action[5:].split('_', 1)  # убираем "city_"
            brand, city = parts[0], parts[1]
            templates = ad_templates.get(brand, {}).get(city, {})
            
            if not templates:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(f"« К городам {brand.upper()}", callback_data=f"ads_brand_{brand}"))
                bot.send_message(chat_id, f"📝 У {brand.upper()} в {city.capitalize()} пока нет шаблонов", reply_markup=markup)
                return
                
            text_lines = [f"📝 ШАБЛОНЫ {brand.upper()} / {city.upper()}\n"]
            for i, (name, content) in enumerate(templates.items(), 1):
                text_lines.append(f"{i}. 🔹 {name}")
                preview = content[:150] + "..." if len(content) > 150 else content
                text_lines.append(f"   {preview}\n")
            
            text = "\n".join(text_lines)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"« К городам {brand.upper()}", callback_data=f"ads_brand_{brand}"))
            bot.send_message(chat_id, text, reply_markup=markup)
            
        elif action == "add_template":
            # КНОПКА: "➕ Добавить шаблон"
            markup = types.InlineKeyboardMarkup()
            
            for brand in ad_templates.keys():
                btn = types.InlineKeyboardButton(
                    f"➕ В {brand.upper()}", 
                    callback_data=f"ads_add_to_{brand}"
                )
                markup.add(btn)
            
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_back_main"))
            bot.send_message(chat_id, "➕ Выберите бренд для добавления шаблона:", reply_markup=markup)
            
        elif action.startswith("add_to_"):
            # Выбор города для добавления
            brand = action[7:]  # убираем "add_to_"
            cities = ad_templates.get(brand, {})
            
            markup = types.InlineKeyboardMarkup()
            for city in cities.keys():
                btn = types.InlineKeyboardButton(
                    f"📍 {city.capitalize()}", 
                    callback_data=f"ads_add_city_{brand}_{city}"
                )
                markup.add(btn)
            
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_add_template"))
            bot.send_message(chat_id, f"📍 Выберите город в {brand.upper()}:", reply_markup=markup)
            
        elif action.startswith("add_city_"):
            # Начать процесс добавления шаблона
            parts = action[9:].split('_', 1)  # убираем "add_city_"
            brand, city = parts[0], parts[1]
            
            # Сохраняем состояние пользователя
            user_id = call.from_user.id
            from .wizards import user_states
            user_states[user_id] = {
                "state": "awaiting_ad_template", 
                "brand": brand, 
                "city": city
            }
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("« Отмена", callback_data="ads_back_main"))
            
            bot.send_message(
                chat_id, 
                f"➕ Добавление шаблона в {brand.upper()} / {city.capitalize()}\n\n"
                f"Отправьте сообщение в формате:\n\n"
                f"Название шаблона\n"
                f"Текст шаблона...\n\n"
                f"Для отмены введите /cancel",
                reply_markup=markup
            )
            
        elif action == "delete_template":
            # КНОПКА: "🗑️ Удалить шаблон"
            markup = types.InlineKeyboardMarkup()
            
            for brand in ad_templates.keys():
                btn = types.InlineKeyboardButton(
                    f"🗑️ Из {brand.upper()}", 
                    callback_data=f"ads_del_from_{brand}"
                )
                markup.add(btn)
            
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_back_main"))
            bot.send_message(chat_id, "🗑️ Выберите бренд для удаления шаблона:", reply_markup=markup)
            
        elif action.startswith("del_from_"):
            # Выбор города для удаления
            brand = action[9:]  # убираем "del_from_"
            cities = ad_templates.get(brand, {})
            
            markup = types.InlineKeyboardMarkup()
            for city, templates in cities.items():
                if templates:  # только города с шаблонами
                    btn = types.InlineKeyboardButton(
                        f"📍 {city.capitalize()} ({len(templates)})", 
                        callback_data=f"ads_del_city_{brand}_{city}"
                    )
                    markup.add(btn)
            
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_delete_template"))
            bot.send_message(chat_id, f"� Выберите город в {brand.upper()}:", reply_markup=markup)
            
        elif action.startswith("del_city_"):
            # Показать шаблоны для удаления
            parts = action[9:].split('_', 1)  # убираем "del_city_"
            brand, city = parts[0], parts[1]
            templates = ad_templates.get(brand, {}).get(city, {})
            
            markup = types.InlineKeyboardMarkup()
            for name in templates.keys():
                btn = types.InlineKeyboardButton(
                    f"🗑️ {name}", 
                    callback_data=f"ads_confirm_del_{brand}_{city}_{name}"
                )
                markup.add(btn)
            
            markup.add(types.InlineKeyboardButton(f"« К городам {brand.upper()}", callback_data=f"ads_del_from_{brand}"))
            bot.send_message(chat_id, f"🗑️ Выберите шаблон для удаления из {brand.upper()} / {city.capitalize()}:", reply_markup=markup)
            
        elif action.startswith("confirm_del_"):
            # Подтверждение удаления
            parts = action[12:].split('_', 2)  # убираем "confirm_del_"
            brand, city, template_name = parts[0], parts[1], parts[2]
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"ads_do_delete_{brand}_{city}_{template_name}"),
                types.InlineKeyboardButton("❌ Отмена", callback_data=f"ads_del_city_{brand}_{city}")
            )
            
            template_content = ad_templates.get(brand, {}).get(city, {}).get(template_name, "")
            preview = template_content[:200] + "..." if len(template_content) > 200 else template_content
            
            bot.send_message(
                chat_id, 
                f"🗑️ ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ\n\n"
                f"Бренд: {brand.upper()}\n"
                f"Город: {city.capitalize()}\n"
                f"Шаблон: {template_name}\n\n"
                f"Содержимое:\n{preview}\n\n"
                f"⚠️ Вы уверены, что хотите удалить этот шаблон?",
                reply_markup=markup
            )
            
        elif action.startswith("do_delete_"):
            # Выполнить удаление
            parts = action[10:].split('_', 2)  # убираем "do_delete_"
            brand, city, template_name = parts[0], parts[1], parts[2]
            
            if template_name in ad_templates.get(brand, {}).get(city, {}):
                del ad_templates[brand][city][template_name]
                
                # Сохранить файл
                try:
                    with open('ad_templates.json', 'w', encoding='utf-8') as f:
                        json.dump(ad_templates, f, ensure_ascii=False, indent=2)
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("« Назад к главному меню", callback_data="ads_back_main"))
                    
                    bot.send_message(
                        chat_id, 
                        f"✅ Шаблон '{template_name}' успешно удален из {brand.upper()} / {city.capitalize()}",
                        reply_markup=markup
                    )
                    
                except Exception as e:
                    bot.send_message(chat_id, f"❌ Ошибка сохранения файла: {e}")
            else:
                bot.send_message(chat_id, "❌ Шаблон не найден")
                
        elif action == "back_main":
            # Вернуться к главному меню
            from .wizards import command_ads_new
            command_ads_new(call.message)
            
        elif action.startswith("replace_"):
            # Заменить существующий шаблон
            parts = action[8:].split('_', 2)  # убираем "replace_"
            brand, city, template_name = parts[0], parts[1], parts[2]
            
            # Получаем новый текст из состояния пользователя
            from .wizards import user_states
            user_id = call.from_user.id
            if user_id not in user_states or "new_template_text" not in user_states[user_id]:
                bot.send_message(chat_id, "❌ Ошибка состояния. Начните заново.")
                return
            
            new_text = user_states[user_id]["new_template_text"]
            
            # Заменяем шаблон
            ad_templates[brand][city][template_name] = new_text
            
            # Сохраняем файл
            try:
                with open('ad_templates.json', 'w', encoding='utf-8') as f:
                    json.dump(ad_templates, f, ensure_ascii=False, indent=2)
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("« Назад к главному меню", callback_data="ads_back_main"))
                
                bot.send_message(
                    chat_id, 
                    f"✅ Шаблон '{template_name}' успешно заменен в {brand.upper()} / {city.capitalize()}!\n\n"
                    f"Новое содержимое:\n{new_text[:200]}{'...' if len(new_text) > 200 else ''}",
                    reply_markup=markup
                )
                
            except Exception as e:
                bot.send_message(chat_id, f"❌ Ошибка сохранения файла: {e}")
            
            # Очищаем состояние
            user_states.pop(user_id, None)
            
            text = "\n".join(text_lines)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"« К городам {brand.upper()}", callback_data=f"ads_brand_{brand}"))
            
            bot.send_message(chat_id, text, reply_markup=markup)
            
        elif action == "back_main":
            # Вернуться к главному меню
            from .wizards import command_ads_new
            command_ads_new(call.message)

    @bot.callback_query_handler(func=lambda call: True)
    def _debug_all_callbacks(call: types.CallbackQuery):
        """Перехватывает все необработанные колбэки для отладки."""
        try:
            bot.answer_callback_query(call.id, f"Необработанный колбэк: {call.data}", show_alert=False)
        except Exception:
            pass
        logging.warning(f"Получен необработанный callback_data -> {call.data} от {get_username(call.from_user)} в чате {call.message.chat.id}")
