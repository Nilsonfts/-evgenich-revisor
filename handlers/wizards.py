# handlers/wizards.py

import logging
import datetime
from telebot import types

from utils import admin_required, save_json_data
from state import user_states, chat_configs, ad_templates
from config import TIMEZONE_MAP, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE

def register_wizard_handlers(bot):

    # ========================================
    #   МАСТЕР НАСТРОЙКИ ЧАТА (/setup_wizard)
    # ========================================

    @bot.message_handler(commands=['setup_wizard'])
    @admin_required(bot)
    def handle_setup_wizard(message: types.Message):
        """Начинает пошаговую настройку чата."""
        chat_id = message.chat.id
        user_id = message.from_user.id
        
        user_states[user_id] = {"state": "wizard_awaiting_brand_city", "chat_id": chat_id, "data": {}}
        
        text = ("🧙‍♂️ **Мастер настройки чата**\n\n"
                "Я задам вам 4 вопроса для полной настройки. "
                "Чтобы отменить настройку на любом шаге, просто отправьте /cancel.\n\n"
                "**Шаг 1 из 4:** Введите **бренд** и **город** для этого чата.\n"
                "*Пример:* `my-brand moscow`")
        msg = bot.send_message(chat_id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_wizard_brand_city, bot)

    def process_wizard_brand_city(message: types.Message, bot):
        """Шаг 1: Обработка бренда и города."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "wizard_awaiting_brand_city": return
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Настройка отменена.")

        try:
            brand, city = message.text.split(maxsplit=1)
            state["data"]["brand"] = brand.lower()
            state["data"]["city"] = city.lower()
            
            state["state"] = "wizard_awaiting_timezone"
            text = ("✅ **Шаг 2 из 4:** Отлично! Теперь укажите **часовой пояс**.\n"
                    "Введите смещение от Москвы. *Пример:* `+3` или `-1`")
            msg = bot.reply_to(message, text, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_timezone, bot)
        except ValueError:
            msg = bot.reply_to(message, "❌ **Ошибка.** Пожалуйста, введите два слова: бренд и город. *Пример:* `my-brand moscow`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_brand_city, bot)
            
    def process_wizard_timezone(message: types.Message, bot):
        """Шаг 2: Обработка часового пояса."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "wizard_awaiting_timezone": return
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Настройка отменена.")
            
        offset = message.text.strip()
        tz_name = TIMEZONE_MAP.get(offset)
        if not tz_name:
            msg = bot.reply_to(message, f"❌ **Ошибка.** Неверный формат смещения. Доступные варианты: {list(TIMEZONE_MAP.keys())}\nПопробуйте еще раз.", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_timezone, bot)
            return
            
        state["data"]["timezone"] = tz_name
        
        state["state"] = "wizard_awaiting_timing"
        text = ("✅ **Шаг 3 из 4:** Часовой пояс установлен! Теперь задайте **график смены**.\n"
                "Введите время начала и конца. *Пример:* `19:00 04:00`")
        msg = bot.reply_to(message, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_wizard_timing, bot)

    def process_wizard_timing(message: types.Message, bot):
        """Шаг 3: Обработка времени смены."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "wizard_awaiting_timing": return
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Настройка отменена.")

        try:
            start_time_str, end_time_str = message.text.split()
            datetime.datetime.strptime(start_time_str, '%H:%M')
            datetime.datetime.strptime(end_time_str, '%H:%M')
            state["data"]["start_time"] = start_time_str
            state["data"]["end_time"] = end_time_str
            
            state["state"] = "wizard_awaiting_goal"
            text = ("✅ **Шаг 4 из 4:** График задан! И последнее: укажите **план (норму) ГС** за смену.\n"
                    "Введите одно число. *Пример:* `25`")
            msg = bot.reply_to(message, text, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_goal, bot)
        except (ValueError, IndexError):
            msg = bot.reply_to(message, "❌ **Ошибка.** Неверный формат. Введите два времени через пробел. *Пример:* `19:00 04:00`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_timing, bot)

    def process_wizard_goal(message: types.Message, bot):
        """Шаг 4: Обработка цели и завершение."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "wizard_awaiting_goal": return
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Настройка отменена.")
            
        try:
            goal = int(message.text)
            if goal <= 0: raise ValueError
            state["data"]["default_goal"] = goal
            
            chat_id_to_configure = str(state["chat_id"])
            if chat_id_to_configure not in chat_configs:
                chat_configs[chat_id_to_configure] = {}
            chat_configs[chat_id_to_configure].update(state["data"])
            save_json_data(CHAT_CONFIG_FILE, chat_configs)
            
            final_text = ("🎉 **Настройка завершена!**\n\n"
                          "Чат успешно настроен со следующими параметрами:\n"
                          f"  - Бренд: `{state['data']['brand']}`\n"
                          f"  - Город: `{state['data']['city']}`\n"
                          f"  - Часовой пояс: `{state['data']['timezone']}`\n"
                          f"  - График: `{state['data']['start_time']}` - `{state['data']['end_time']}`\n"
                          f"  - Норма ГС: `{state['data']['default_goal']}`\n\n"
                          "Бот готов к работе в этом чате!")
            bot.reply_to(message, final_text, parse_mode="Markdown")
            
        except (ValueError, IndexError):
            msg = bot.reply_to(message, "❌ **Ошибка.** Введите целое положительное число. *Пример:* `25`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_goal, bot)
        finally:
            if user_id in user_states:
                del user_states[user_id]
    
    # ========================================
    #   УПРАВЛЕНИЕ РЕКЛАМОЙ (/ads)
    # ========================================
    
    @bot.message_handler(commands=['ads'])
    @admin_required(bot)
    def command_ads(message: types.Message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        brands = list(ad_templates.keys())
        for brand in brands:
            markup.add(types.InlineKeyboardButton(brand.upper(), callback_data=f"ad_brand_{brand}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить новый бренд", callback_data="ad_addbrand_form"))
        bot.send_message(message.chat.id, "📝 Выберите бренд для управления рекламой:", reply_markup=markup)
    
    def show_ad_cities_menu(bot, chat_id: int, brand: str):
        markup = types.InlineKeyboardMarkup(row_width=2)
        cities = list(ad_templates.get(brand, {}).keys())
        for city in cities:
            markup.add(types.InlineKeyboardButton(city.capitalize(), callback_data=f"ad_city_{brand}_{city}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить новый город", callback_data=f"ad_addcity_form_{brand}"))
        markup.add(types.InlineKeyboardButton("« Назад к брендам", callback_data="ad_backtobrand"))
        bot.send_message(chat_id, f"Бренд: *{brand.upper()}*\nВыберите город:", reply_markup=markup, parse_mode="Markdown")
    
    def show_ad_actions_menu(bot, chat_id: int, brand: str, city: str):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👁️‍🗨️ Просмотреть шаблоны", callback_data=f"ad_view_{brand}_{city}"),
            types.InlineKeyboardButton("➕ Добавить шаблон", callback_data=f"ad_addform_{brand}_{city}"),
            types.InlineKeyboardButton("➖ Удалить шаблон", callback_data=f"ad_delform_{brand}_{city}"),
            types.InlineKeyboardButton("« Назад к городам", callback_data=f"ad_backtocity_{brand}")
        )
        bot.send_message(chat_id, f"Бренд: *{brand.upper()}* / Город: *{city.capitalize()}*\nВыберите действие:", reply_markup=markup, parse_mode="Markdown")

    def show_templates_for_deletion(bot, chat_id: int, brand: str, city: str):
        templates = ad_templates.get(brand, {}).get(city, {})
        if not templates:
            bot.send_message(chat_id, "Здесь нет шаблонов для удаления.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for tpl_key in templates.keys():
            markup.add(types.InlineKeyboardButton(f"❌ {tpl_key}", callback_data=f"ad_delete_{brand}_{city}_{tpl_key}"))
        markup.add(types.InlineKeyboardButton("« Назад", callback_data=f"ad_city_{brand}_{city}"))
        bot.send_message(chat_id, "Выберите шаблон для удаления:", reply_markup=markup)

    @bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get("state") == "awaiting_ad_template")
    def receive_ad_template_to_add(message: types.Message):
        user_id = message.from_user.id
        state = user_states.get(user_id)
        if not state: return

        if message.text == '/cancel':
            del user_states[user_id]
            return bot.send_message(message.chat.id, "Добавление шаблона отменено.")
        try:
            name, text = message.text.split('\n', 1)
            name, text = name.strip(), text.strip()
            if not name or not text: raise ValueError
            
            brand, city = state['brand'], state['city']
            if brand not in ad_templates: ad_templates[brand] = {}
            if city not in ad_templates[brand]: ad_templates[brand][city] = {}
            ad_templates[brand][city][name] = text

            if save_json_data(AD_TEMPLATES_FILE, ad_templates):
                bot.send_message(message.chat.id, f"✅ Шаблон *'{name}'* успешно добавлен для *{brand.upper()}/{city.capitalize()}*.", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ Ошибка сохранения файла шаблонов.")
            
            del user_states[user_id]
        except (ValueError, KeyError):
            bot.send_message(message.chat.id, "Неверный формат. Пожалуйста, отправьте сообщение в формате:\n\n`Название шаблона`\n`Текст шаблона...`", parse_mode="Markdown")
