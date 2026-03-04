# handlers/callbacks.py

import logging
import random
from telebot import types

from utils import is_admin, get_username, init_user_data, save_json_data, save_history_event
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
        
        # Сохраняем роль передающего и назначаем её принимающему
        from_role = getattr(shift.users.get(transfer_info['from_id'], None), 'role', 'караоке_ведущий') if transfer_info['from_id'] in shift.users else 'караоке_ведущий'
        from_goal = getattr(shift.users.get(transfer_info['from_id'], None), 'goal', 15) if transfer_info['from_id'] in shift.users else 15
        
        if transfer_info['to_id'] not in shift.users:
            shift.users[transfer_info['to_id']] = init_user_data(transfer_info['to_id'], transfer_info['to_username'], from_role)
            shift.users[transfer_info['to_id']].goal = from_goal
        else:
            shift.users[transfer_info['to_id']].role = from_role
            shift.users[transfer_info['to_id']].goal = from_goal

        del pending_transfers[chat_id]
        
        bot.answer_callback_query(call.id, "Смена принята!")
        try: bot.delete_message(chat_id, call.message.message_id)
        except Exception: pass
        
        phrase_template = random.choice(soviet_phrases.get("system_messages", {}).get('shift_transfer_success', ["."]))
        text = phrase_template.format(from_username=transfer_info['from_username'], to_username=transfer_info['to_username'])
        bot.send_message(chat_id, text)
        save_history_event(chat_id, user_id, transfer_info['to_username'], f"Принял смену от {transfer_info['from_username']}")

    # Обработчики для системы рекламы /ads
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

    # Обработчик кнопки "Завершить паузу"
    @bot.callback_query_handler(func=lambda call: call.data.startswith('stop_pause_'))
    def handle_stop_pause_callback(call: types.CallbackQuery):
        """Обработка кнопки завершения паузы."""
        import datetime
        import pytz
        
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        target_user_id = int(call.data.replace('stop_pause_', ''))
        
        if user_id != target_user_id:
            return bot.answer_callback_query(call.id, "Эта кнопка не для вас.", show_alert=True)
        
        shift = chat_data.get(chat_id)
        if not shift or user_id not in shift.users:
            return bot.answer_callback_query(call.id, "Вы не на смене.", show_alert=True)
        
        user_data = shift.users.get(user_id)
        if not user_data or not user_data.on_pause:
            return bot.answer_callback_query(call.id, "Пауза не активна.", show_alert=True)
        
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
        pause_duration = (now_moscow - pause_start).total_seconds() / 60
        
        user_data.on_pause = False
        user_data.pause_end_time = now_moscow.isoformat()
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        
        bot.answer_callback_query(call.id, "⏯️ Пауза снята!")
        bot.send_message(chat_id, 
            f"⏯️ **ПАУЗА КОНЧИЛАСЬ!** Возвращайся на 'базу' 🗣️\n\n"
            f"✅ Счётчики снова тикают\n"
            f"📊 Пауза длилась: {int(pause_duration)} мин\n"
            f"🎯 Давай, покажи, на что способен! 💪",
            parse_mode="Markdown")
    
    # Обработчики для маркетинговой аналитики (кнопки из admin.py)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('marketing_'))
    def handle_marketing_callbacks(call: types.CallbackQuery):
        """Обработчик для кнопок маркетинговой аналитики."""
        if not is_admin(bot, call.from_user.id, call.message.chat.id):
            return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
        
        chat_id = call.message.chat.id
        action = call.data
        
        if action == "marketing_detailed":
            bot.answer_callback_query(call.id, "📊 Формирую детальный отчет...")
            from database_manager import db
            analytics = db.get_marketing_analytics(chat_id, days=30)
            if not analytics:
                bot.send_message(chat_id, "❌ Недостаточно данных для детального отчета.")
                return
            text = "📊 **Детальный маркетинговый отчет** (30 дней)\n\n"
            text += f"• Смен проведено: {analytics.get('total_shifts', 0)}\n"
            text += f"• Среднее выполнение: {analytics.get('avg_plan_completion', 0):.1f}%\n"
            text += f"• Общее время: {analytics.get('total_active_time', 0):.1f} часов\n"
            text += f"• Средний ритм: {analytics.get('avg_rhythm', 0):.1f} мин/ГС\n"
            text += f"• Опозданий: {analytics.get('total_late_returns', 0)}\n"
            bot.send_message(chat_id, text, parse_mode="Markdown")
            
        elif action == "marketing_trends":
            bot.answer_callback_query(call.id, "📈 Анализирую тренды...")
            from database_manager import db
            analytics_7 = db.get_marketing_analytics(chat_id, days=7)
            analytics_30 = db.get_marketing_analytics(chat_id, days=30)
            if not analytics_7 or not analytics_30:
                bot.send_message(chat_id, "❌ Недостаточно данных для анализа трендов.")
                return
            avg_7 = analytics_7.get('avg_plan_completion', 0)
            avg_30 = analytics_30.get('avg_plan_completion', 0)
            trend = "📈 Рост" if avg_7 > avg_30 else "📉 Снижение" if avg_7 < avg_30 else "➡️ Стабильно"
            text = f"📈 **Тренды**\n\n"
            text += f"• Выполнение за 7 дней: {avg_7:.1f}%\n"
            text += f"• Выполнение за 30 дней: {avg_30:.1f}%\n"
            text += f"• Тренд: {trend}\n"
            bot.send_message(chat_id, text, parse_mode="Markdown")
            
        elif action == "marketing_recommendations":
            bot.answer_callback_query(call.id, "💡 Формирую рекомендации...")
            from database_manager import db
            analytics = db.get_marketing_analytics(chat_id, days=7)
            if not analytics:
                bot.send_message(chat_id, "❌ Недостаточно данных для рекомендаций.")
                return
            recs = ["💡 **Рекомендации**\n"]
            avg_completion = analytics.get('avg_plan_completion', 0)
            if avg_completion < 70:
                recs.append("⚠️ Выполнение ниже 70% — рассмотрите снижение целей или дополнительную мотивацию.")
            elif avg_completion < 90:
                recs.append("👍 Показатели хорошие, есть потенциал для роста.")
            else:
                recs.append("✅ Отличные результаты! Можно рассмотреть повышение целей.")
            avg_rhythm = analytics.get('avg_rhythm', 0)
            if avg_rhythm > 5:
                recs.append("🐌 Средний ритм низкий — стоит работать над темпом.")
            total_lates = analytics.get('total_late_returns', 0)
            if total_lates > 3:
                recs.append("⏳ Много опозданий с перерывов — рекомендуется контроль.")
            bot.send_message(chat_id, "\n".join(recs), parse_mode="Markdown")
    
    # Обработчики для подтверждений
    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_'))
    def handle_confirmation_callbacks(call: types.CallbackQuery):
        """Обработчик для кнопок подтверждения действий."""
        logging.info(f"[CONFIRM] Получен callback: data={call.data}, user={call.from_user.id}, chat={call.message.chat.id}")
        try:
            chat_id = call.message.chat.id
            user_id = call.from_user.id
            action = call.data
            
            if action == "confirm_gameover":
                shift = chat_data.get(chat_id)
                if not shift or user_id not in shift.users:
                    return bot.answer_callback_query(call.id, "Вы не участвуете в смене.", show_alert=True)
                
                bot.answer_callback_query(call.id, "🏁 Завершаю смену...")
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                
                from scheduler import send_end_of_shift_report_for_chat
                bot.send_message(chat_id, "📊 Формирую финальный отчет...", parse_mode=None)
                
                try:
                    send_end_of_shift_report_for_chat(bot, chat_id)
                    logging.info(f"Смена в чате {chat_id} завершена /gameover пользователем {user_id}")
                except Exception as e:
                    logging.error(f"Ошибка /gameover в чате {chat_id}: {e}")
                    bot.send_message(chat_id, "❌ Ошибка при завершении смены.", parse_mode=None)
                    
            elif action == "confirm_gameover_cancel":
                bot.answer_callback_query(call.id, "Отменено")
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                bot.send_message(chat_id, "✅ Завершение отменено. Продолжаем!", parse_mode=None)
                
            elif action == "confirm_restart":
                logging.info(f"[CONFIRM_RESTART] user={user_id} chat={chat_id}")
                # Отвечаем на callback СРАЗУ, чтобы кнопка не зависала
                bot.answer_callback_query(call.id, "🔄 Сбрасываю...")
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                from utils import init_shift_data
                init_shift_data(chat_id)
                logging.info(f"[CONFIRM_RESTART] Смена сброшена для чата {chat_id}")
                bot.send_message(chat_id, "🔄 Смена сброшена админом! Все счётчики на нуле. Таков путь.", parse_mode=None)
                # Сохраняем состояние сразу, чтобы сброс не потерялся
                try:
                    from state_manager import save_state
                    from state import chat_data, user_history
                    save_state(bot, chat_data, user_history)
                except Exception as save_err:
                    logging.warning(f"[CONFIRM_RESTART] Не удалось сохранить состояние: {save_err}")
                
            elif action == "confirm_restart_cancel":
                bot.answer_callback_query(call.id, "Отменено")
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                
            elif action == "confirm_report":
                bot.answer_callback_query(call.id, "Формирую...") 
                if not is_admin(bot, user_id, chat_id):
                    return bot.send_message(chat_id, "❌ Нет прав", parse_mode=None)
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                from scheduler import send_end_of_shift_report_for_chat
                bot.send_message(chat_id, "⏳ Формирую отчёт...", parse_mode=None)
                send_end_of_shift_report_for_chat(bot, chat_id)
                
            elif action == "confirm_report_cancel":
                bot.answer_callback_query(call.id, "Отменено")
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
            else:
                logging.warning(f"[CONFIRM] Неизвестный action: {action}")
                bot.answer_callback_query(call.id)
        except Exception as e:
            logging.error(f"[CONFIRM] ОШИБКА: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)
            except Exception:
                pass
    
    # Обработчик выбора роли при /start
    @bot.callback_query_handler(func=lambda call: call.data.startswith('role_select_'))
    def handle_role_selection(call: types.CallbackQuery):
        """Обработка выбора роли при старте смены в выходные."""
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        role = call.data.replace('role_select_', '')
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        
        # Создаем фейковое сообщение для handle_start
        bot.answer_callback_query(call.id, f"Выбрана роль: {role}")
        
        # Формируем фейковое сообщение со специальным текстом для handle_start
        role_map = {
            'karaoke': 'караоке',
            'mc': 'МС'
        }
        role_text = role_map.get(role, role)
        
        # Создаём фейковое сообщение и отправляем через process_new_messages
        try:
            import time as time_mod
            fake_json = {
                'message_id': call.message.message_id,
                'from': {
                    'id': call.from_user.id,
                    'is_bot': False,
                    'first_name': call.from_user.first_name or '',
                    'username': call.from_user.username or ''
                },
                'chat': {
                    'id': call.message.chat.id,
                    'type': call.message.chat.type
                },
                'date': int(time_mod.time()),
                'text': f'/start {role_text}'
            }
            fake_msg = types.Message.de_json(fake_json)
            bot.process_new_messages([fake_msg])
        except Exception as e:
            logging.error(f"Ошибка при выборе роли: {e}")
            bot.send_message(chat_id, f"👉 Отправьте: `/start {role_text}`", parse_mode="Markdown")
    
    # Обработчик кнопки "Отклонить передачу"
    @bot.callback_query_handler(func=lambda call: call.data.startswith('transfer_decline_'))
    def handle_transfer_decline(call: types.CallbackQuery):
        """Обработка отклонения передачи смены."""
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        if chat_id not in pending_transfers:
            return bot.answer_callback_query(call.id, "Предложение уже неактуально.", show_alert=True)
        
        transfer_info = pending_transfers[chat_id]
        
        if user_id != transfer_info['to_id']:
            return bot.answer_callback_query(call.id, "Это предложение адресовано не вам.", show_alert=True)
        
        # Отменяем таймер
        transfer_info['timer'].cancel()
        del pending_transfers[chat_id]
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        
        bot.answer_callback_query(call.id, "Передача отклонена")
        bot.send_message(chat_id, 
            f"❌ {transfer_info['to_username']} сказал(a) 'ухади' предложению от {transfer_info['from_username']}. 🚪 Смена остаётся на месте!")
        save_history_event(chat_id, user_id, transfer_info['to_username'], 
            f"Отклонил передачу смены от {transfer_info['from_username']}")
