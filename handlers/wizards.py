# handlers/wizards.py

import logging
import datetime
from telebot import types

from utils import admin_required, save_json_data
from state import user_states, chat_configs, ad_templates
from config import TIMEZONE_MAP, CHAT_CONFIG_FILE, AD_TEMPLATES_FILE

# Доступные концепции
AVAILABLE_CONCEPTS = {
    "РВБ": {"name": "РВБ", "description": "Концепция РВБ - романтический вечер для двоих"},
    "НЕБАР": {"name": "НЕБАР", "description": "НЕБАР - неформальный бар с живой атмосферой"},
    "ЕВГЕНИЧ": {"name": "ЕВГЕНИЧ", "description": "ЕВГЕНИЧ - классическое караоке"},
    "СПЛЕТНИ": {"name": "СПЛЕТНИ", "description": "СПЛЕТНИ - уютная атмосфера для откровенных разговоров"},
    "ОРБИТА": {"name": "ОРБИТА", "description": "ОРБИТА - космическая тематика"}
}

# Предопределенные категории рекламы с AI-помощью
AD_CATEGORIES = {
    "menu": {"name": "🍽️ Меню", "keywords": ["меню", "блюдо", "кухня", "еда", "напиток", "коктейль", "пицца", "суши"]},
    "events": {"name": "🎉 События", "keywords": ["вечеринка", "корпоратив", "день рождения", "праздник", "мероприятие", "свадьба", "выпускной"]},
    "promo": {"name": "🎁 Акции", "keywords": ["скидка", "акция", "промо", "бесплатно", "подарок", "бонус", "распродажа", "специальная цена"]},
    "karaoke": {"name": "🎤 Караоке", "keywords": ["караоке", "песня", "микрофон", "сцена", "пение", "конкурс", "голос", "музыка"]},
    "booking": {"name": "📅 Бронь", "keywords": ["бронирование", "столик", "резерв", "место", "заказ", "зал", "кабинка", "vip"]},
    "entertainment": {"name": "🎮 Развлечения", "keywords": ["игра", "бильярд", "дартс", "настольная", "развлечение", "турнир", "championship"]},
    "drinks": {"name": "🍺 Напитки", "keywords": ["пиво", "вино", "коктейль", "виски", "водка", "шампанское", "бар", "алкоголь"]},
    "loyalty": {"name": "💎 Лояльность", "keywords": ["постоянный клиент", "программа лояльности", "карта", "накопительная", "vip", "статус"]},
    "general": {"name": "📢 Общее", "keywords": ["работаем", "открыты", "график", "контакты", "адрес", "информация", "новости"]}
}

def categorize_ad_text(text: str) -> str:
    """Автоматически определяет категорию рекламного текста."""
    text_lower = text.lower()
    scores = {}
    
    for category_id, category_data in AD_CATEGORIES.items():
        score = 0
        for keyword in category_data["keywords"]:
            if keyword in text_lower:
                score += 1
        scores[category_id] = score
    
    # Возвращаем категорию с наибольшим количеством совпадений
    best_category = max(scores, key=scores.get)
    return best_category if scores[best_category] > 0 else "general"

def register_wizard_handlers(bot):

    # ========================================
    #   МАСТЕР НАСТРОЙКИ ЧАТА (/setup_wizard)
    # ========================================

    @bot.message_handler(commands=['setup_wizard'])
    @admin_required(bot)
    def handle_setup_wizard(message: types.Message):
        """Полная настройка чата в 4 шага."""
        chat_id = message.chat.id
        
        # Инициализируем временное состояние для мастера
        if str(chat_id) not in user_states:
            user_states[str(chat_id)] = {}
        
        user_states[str(chat_id)]["setup_step"] = "city"
        user_states[str(chat_id)]["setup_data"] = {}
        
        text = ("🧙‍♂️ **Мастер настройки чата**\n\n"
                "✅ **Шаг 1 из 4: Укажите город**\n"
                "Введите название города, где работает заведение.\n"
                "Пример: Москва, Санкт-Петербург, Казань\n\n"
                "💬 Введите название города:")
        
        msg = bot.send_message(chat_id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_city_input)

    def process_city_input(message: types.Message):
        """Обработка ввода города."""
        chat_id = str(message.chat.id)
        city = message.text.strip()
        
        if len(city) < 2:
            text = "❌ Название города слишком короткое. Попробуйте еще раз:"
            msg = bot.send_message(message.chat.id, text)
            bot.register_next_step_handler(msg, process_city_input)
            return
        
        # Сохраняем город
        user_states[chat_id]["setup_data"]["city"] = city
        
        text = ("✅ **Шаг 2 из 4: Отлично! Теперь укажите часовой пояс.**\n"
                "Введите смещение от Москвы. Пример: +3 или -1\n\n"
                "💬 Введите смещение:")
        
        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_timezone_input)

    def process_timezone_input(message: types.Message):
        """Обработка ввода часового пояса."""
        chat_id = str(message.chat.id)
        timezone_input = message.text.strip()
        
        # Проверяем формат (+3, -1, etc.)
        try:
            if timezone_input.startswith(('+', '-')):
                offset = int(timezone_input)
                if -12 <= offset <= 12:
                    user_states[chat_id]["setup_data"]["timezone"] = offset
                    
                    text = ("✅ **Шаг 3 из 4: Часовой пояс установлен! Теперь задайте график смены.**\n"
                            "Введите время начала и конца. Пример: 19:00 04:00\n\n"
                            "💬 Введите график:")
                    
                    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
                    bot.register_next_step_handler(msg, process_schedule_input)
                    return
        except ValueError:
            pass
        
        text = ("❌ Неверный формат часового пояса.\n"
                "Введите смещение от Москвы. Пример: +3 или -1\n\n"
                "💬 Попробуйте еще раз:")
        
        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_timezone_input)

    def process_schedule_input(message: types.Message):
        """Обработка ввода графика смены."""
        chat_id = str(message.chat.id)
        schedule_input = message.text.strip()
        
        # Простая проверка формата времени
        try:
            parts = schedule_input.split()
            if len(parts) == 2:
                start_time, end_time = parts
                # Проверяем формат времени (HH:MM)
                if ':' in start_time and ':' in end_time:
                    start_hour, start_min = map(int, start_time.split(':'))
                    end_hour, end_min = map(int, end_time.split(':'))
                    
                    if (0 <= start_hour <= 23 and 0 <= start_min <= 59 and 
                        0 <= end_hour <= 23 and 0 <= end_min <= 59):
                        
                        user_states[chat_id]["setup_data"]["schedule"] = {
                            "start": start_time,
                            "end": end_time
                        }
                        
                        text = ("✅ **Шаг 4 из 4: График задан! И последнее: укажите план (норму) ГС за смену.**\n"
                                "Введите одно число. Пример: 25\n\n"
                                "💬 Введите план:")
                        
                        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
                        bot.register_next_step_handler(msg, process_plan_input)
                        return
        except ValueError:
            pass
        
        text = ("❌ Неверный формат времени.\n"
                "Введите время начала и конца. Пример: 19:00 04:00\n\n"
                "💬 Попробуйте еще раз:")
        
        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_schedule_input)

    def process_plan_input(message: types.Message):
        """Обработка ввода плана ГС."""
        chat_id = str(message.chat.id)
        plan_input = message.text.strip()
        
        try:
            plan = int(plan_input)
            if plan > 0:
                user_states[chat_id]["setup_data"]["plan_voices"] = plan
                
                # Теперь запрашиваем концепцию
                text = ("✅ **Финальный шаг: Выберите концепцию заведения**\n\n"
                        "📋 **Доступные концепции:**\n"
                        "• РВБ - романтический вечер для двоих\n"
                        "• ЕВГЕНИЧ - классическое караоке\n"
                        "• НЕБАР - неформальный бар\n"
                        "• СПЛЕТНИ - уютная атмосфера\n"
                        "• ОРБИТА - космическая тематика\n\n"
                        "💬 Введите название концепции:")
                
                msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
                bot.register_next_step_handler(msg, process_concept_input)
                return
        except ValueError:
            pass
        
        text = ("❌ Введите корректное число.\n"
                "Пример: 25\n\n"
                "💬 Попробуйте еще раз:")
        
        msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_plan_input)

    def process_concept_input(message: types.Message):
        """Обработка ввода концепции и завершение настройки."""
        concept_input = message.text.strip().upper()
        chat_id = str(message.chat.id)
        
        # Список доступных концепций
        available_concepts = ["РВБ", "ЕВГЕНИЧ", "НЕБАР", "СПЛЕТНИ", "ОРБИТА"]
        
        if concept_input in available_concepts:
            # Получаем все собранные данные
            setup_data = user_states[chat_id]["setup_data"]
            
            # Сохраняем полную конфигурацию
            if chat_id not in chat_configs:
                chat_configs[chat_id] = {}
            
            chat_configs[chat_id].update({
                "concept": concept_input,
                "city": setup_data["city"],
                "timezone": setup_data["timezone"],
                "schedule": setup_data["schedule"],
                "plan_voices": setup_data["plan_voices"],
                "configured_at": datetime.datetime.now().isoformat()
            })
            
            save_json_data(CHAT_CONFIG_FILE, chat_configs)
            
            # Очищаем временное состояние
            if "setup_step" in user_states[chat_id]:
                del user_states[chat_id]["setup_step"]
            if "setup_data" in user_states[chat_id]:
                del user_states[chat_id]["setup_data"]
            
            # Формируем итоговое сообщение
            schedule = setup_data["schedule"]
            timezone_str = f"+{setup_data['timezone']}" if setup_data['timezone'] >= 0 else str(setup_data['timezone'])
            
            text = (f"🎉 **Настройка завершена!**\n\n"
                    f"📍 **Город:** {setup_data['city']}\n"
                    f"🕐 **Часовой пояс:** МСК{timezone_str}\n"
                    f"📅 **График смены:** {schedule['start']} - {schedule['end']}\n"
                    f"🎯 **План ГС за смену:** {setup_data['plan_voices']}\n"
                    f"🏢 **Концепция:** {concept_input}\n\n"
                    f"✅ Чат готов к работе!")
            
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            
            logging.info(f"Chat {chat_id} fully configured: {chat_configs[chat_id]}")
        else:
            text = (f"❌ **Неизвестная концепция: {concept_input}**\n\n"
                    "📋 **Доступные концепции:**\n"
                    "• РВБ\n"
                    "• ЕВГЕНИЧ\n"
                    "• НЕБАР\n"
                    "• СПЛЕТНИ\n"
                    "• ОРБИТА\n\n"
                    "💬 Попробуйте еще раз:")
            
            msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_concept_input)
    
    # ========================================
    #   НОВАЯ СИСТЕМА УПРАВЛЕНИЯ РЕКЛАМОЙ (/ads)
    # ========================================
    
    @bot.message_handler(commands=['ads'])
    @admin_required(bot)
    def command_ads_new(message: types.Message):
        """Новая система управления рекламой с категориями."""
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить рекламу", callback_data="ads_add_new"),
            types.InlineKeyboardButton("📁 Просмотр по категориям", callback_data="ads_view_categories")
        )
        markup.add(
            types.InlineKeyboardButton("🔍 Поиск рекламы", callback_data="ads_search"),
            types.InlineKeyboardButton("📊 Статистика", callback_data="ads_stats")
        )
        
        text = ("🎯 **Система управления рекламой 2.0**\n\n"
                "**Новые возможности:**\n"
                "• Автоматическая категоризация текстов\n"
                "• Умный поиск по ключевым словам\n"
                "• Статистика использования\n"
                "• Простое добавление и редактирование\n\n"
                "Выберите действие:")
        
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    
    def show_ad_categories_menu(bot, chat_id: int):
        """Показать меню выбора категорий."""
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        for category_id, category_data in AD_CATEGORIES.items():
            # Подсчитываем количество объявлений в каждой категории
            count = sum(1 for brand_data in ad_templates.values() 
                       for city_data in brand_data.values() 
                       for ads in city_data.values() 
                       for ad in ads if ad.get("category") == category_id)
            
            markup.add(types.InlineKeyboardButton(
                f"{category_data['name']} ({count})", 
                callback_data=f"ads_category_{category_id}"
            ))
        
        markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_back_main"))
        
        bot.send_message(chat_id, "📁 **Категории рекламы:**\nВыберите категорию для просмотра:", 
                        parse_mode="Markdown", reply_markup=markup)
    
    def show_ads_in_category(bot, chat_id: int, category_id: str):
        """Показать все объявления в определенной категории."""
        category_name = AD_CATEGORIES.get(category_id, {}).get("name", "Неизвестная")
        ads_in_category = []
        
        # Собираем все объявления этой категории
        for brand, brand_data in ad_templates.items():
            for city, city_data in brand_data.items():
                for ad_type, ads_list in city_data.items():
                    for i, ad in enumerate(ads_list):
                        if ad.get("category") == category_id:
                            ads_in_category.append({
                                "brand": brand,
                                "city": city,
                                "type": ad_type,
                                "index": i,
                                "text": ad.get("text", ""),
                                "created": ad.get("created", "Неизвестно")
                            })
        
        if not ads_in_category:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("« Назад к категориям", callback_data="ads_view_categories"))
            bot.send_message(chat_id, f"📁 **{category_name}**\n\nВ этой категории пока нет объявлений.", 
                           parse_mode="Markdown", reply_markup=markup)
            return
        
        # Показываем список объявлений
        text = f"📁 **{category_name}** ({len(ads_in_category)} объявлений)\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, ad in enumerate(ads_in_category[:10]):  # Показываем только первые 10
            preview = ad["text"][:50] + "..." if len(ad["text"]) > 50 else ad["text"]
            markup.add(types.InlineKeyboardButton(
                f"{ad['brand']}/{ad['city']} - {preview}",
                callback_data=f"ads_view_{ad['brand']}_{ad['city']}_{ad['type']}_{ad['index']}"
            ))
        
        if len(ads_in_category) > 10:
            text += f"*Показаны первые 10 из {len(ads_in_category)} объявлений*\n\n"
        
        markup.add(types.InlineKeyboardButton("« Назад к категориям", callback_data="ads_view_categories"))
        
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    
    def start_add_ad_wizard(bot, chat_id: int, user_id: int):
        """Начинает процесс добавления нового объявления."""
        user_states[user_id] = {
            "state": "ads_wizard_awaiting_brand", 
            "chat_id": chat_id,
            "ad_data": {}
        }
        
        text = ("➕ **Добавление нового объявления**\n\n"
                "**Шаг 1 из 4:** Введите **бренд** для объявления.\n"
                "*Пример:* `my-brand`\n\n"
                "Или отправьте /cancel для отмены.")
        
        msg = bot.send_message(chat_id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ad_brand, bot)
    
    def process_ad_brand(message: types.Message, bot):
        """Обработка бренда для объявления."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "ads_wizard_awaiting_brand":
            return
        
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Добавление объявления отменено.")
        
        brand = message.text.strip().lower()
        state["ad_data"]["brand"] = brand
        state["state"] = "ads_wizard_awaiting_city"
        
        text = ("✅ **Шаг 2 из 4:** Введите **город** для объявления.\n"
                "*Пример:* `moscow`")
        
        msg = bot.reply_to(message, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ad_city, bot)
    
    def process_ad_city(message: types.Message, bot):
        """Обработка города для объявления."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "ads_wizard_awaiting_city":
            return
        
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Добавление объявления отменено.")
        
        city = message.text.strip().lower()
        state["ad_data"]["city"] = city
        state["state"] = "ads_wizard_awaiting_type"
        
        # Показываем типы объявлений
        markup = types.InlineKeyboardMarkup(row_width=2)
        ad_types = ["вечерняя", "дневная", "акция", "общая"]
        for ad_type in ad_types:
            markup.add(types.InlineKeyboardButton(
                ad_type.capitalize(), 
                callback_data=f"ads_wizard_type_{ad_type}"
            ))
        
        text = ("✅ **Шаг 3 из 4:** Выберите **тип** объявления:")
        
        bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)
    
    def process_ad_text(message: types.Message, bot):
        """Обработка текста объявления."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "ads_wizard_awaiting_text":
            return
        
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Добавление объявления отменено.")
        
        ad_text = message.text.strip()
        
        # Автоматически определяем категорию с помощью AI
        category = categorize_ad_text(ad_text)
        category_name = AD_CATEGORIES.get(category, {}).get("name", "Неизвестно")
        
        # Сохраняем объявление
        brand = state["ad_data"]["brand"]
        city = state["ad_data"]["city"]
        ad_type = state["ad_data"]["type"]
        
        # Создаем структуру если её нет
        if brand not in ad_templates:
            ad_templates[brand] = {}
        if city not in ad_templates[brand]:
            ad_templates[brand][city] = {}
        if ad_type not in ad_templates[brand][city]:
            ad_templates[brand][city][ad_type] = []
        
        # Создаем новое объявление с метаданными
        new_ad = {
            "text": ad_text,
            "category": category,
            "created": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
            "created_by": message.from_user.username or message.from_user.first_name
        }
        
        ad_templates[brand][city][ad_type].append(new_ad)
        
        # Сохраняем в файл
        save_json_data(AD_TEMPLATES_FILE, ad_templates)
        
        final_text = (f"🎉 **Объявление успешно добавлено!**\n\n"
                     f"**Бренд:** {brand.upper()}\n"
                     f"**Город:** {city.capitalize()}\n"
                     f"**Тип:** {ad_type.capitalize()}\n"
                     f"**Категория:** {category_name}\n"
                     f"**Автор:** {new_ad['created_by']}\n\n"
                     f"**Текст:**\n{ad_text}")
        
        bot.reply_to(message, final_text, parse_mode="Markdown")
        
        # Очищаем состояние
        del user_states[user_id]
    
    # Обработчик для выбора типа объявления
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ads_wizard_type_"))
    def handle_ad_type_callback(call):
        """Обработка выбора типа объявления."""
        user_id = call.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "ads_wizard_awaiting_type":
            return
        
        ad_type = call.data.replace("ads_wizard_type_", "")
        state["ad_data"]["type"] = ad_type
        state["state"] = "ads_wizard_awaiting_text"
        
        text = (f"✅ **Тип выбран:** {ad_type.capitalize()}\n\n"
                "**Шаг 4 из 4:** Введите **текст объявления**.\n"
                "Система автоматически определит категорию на основе содержания.\n\n"
                "*Совет:* Используйте ключевые слова как 'скидка', 'караоке', 'меню' для точной категоризации.")
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id, f"Тип: {ad_type}")
        
        # Отправляем новое сообщение для следующего шага
        msg = bot.send_message(call.message.chat.id, "Теперь введите текст объявления:")
        bot.register_next_step_handler(msg, process_ad_text, bot)
    
    # Обработчики для редактирования и удаления
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ads_edit_"))
    def handle_ad_edit_callback(call):
        """Обработка редактирования объявления."""
        try:
            parts = call.data.replace("ads_edit_", "").split("_")
            if len(parts) >= 4:
                brand, city, ad_type, index = parts[0], parts[1], parts[2], int(parts[3])
                start_edit_ad_wizard(bot, call.message.chat.id, call.from_user.id, brand, city, ad_type, index)
                bot.answer_callback_query(call.id, "Начинаем редактирование")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ads_delete_"))
    def handle_ad_delete_callback(call):
        """Обработка удаления объявления."""
        try:
            parts = call.data.replace("ads_delete_", "").split("_")
            if len(parts) >= 4:
                brand, city, ad_type, index = parts[0], parts[1], parts[2], int(parts[3])
                delete_ad(bot, call.message.chat.id, brand, city, ad_type, index)
                bot.answer_callback_query(call.id, "Объявление удалено")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
    
    def start_edit_ad_wizard(bot, chat_id: int, user_id: int, brand: str, city: str, ad_type: str, index: int):
        """Начинает процесс редактирования объявления."""
        try:
            ad = ad_templates[brand][city][ad_type][index]
            
            user_states[user_id] = {
                "state": "ads_edit_awaiting_text",
                "chat_id": chat_id,
                "edit_data": {
                    "brand": brand,
                    "city": city,
                    "type": ad_type,
                    "index": index,
                    "original_text": ad["text"]
                }
            }
            
            text = (f"✏️ **Редактирование объявления**\n\n"
                   f"**Текущий текст:**\n{ad['text']}\n\n"
                   f"Введите новый текст или отправьте /cancel для отмены:")
            
            msg = bot.send_message(chat_id, text, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_edit_ad_text, bot)
            
        except (KeyError, IndexError):
            bot.send_message(chat_id, "❌ Объявление не найдено.")
    
    def process_edit_ad_text(message: types.Message, bot):
        """Обработка нового текста при редактировании."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "ads_edit_awaiting_text":
            return
        
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Редактирование отменено.")
        
        edit_data = state["edit_data"]
        new_text = message.text.strip()
        
        try:
            # Обновляем объявление
            brand, city, ad_type, index = edit_data["brand"], edit_data["city"], edit_data["type"], edit_data["index"]
            
            # Автоматически определяем новую категорию
            new_category = categorize_ad_text(new_text)
            
            ad_templates[brand][city][ad_type][index].update({
                "text": new_text,
                "category": new_category,
                "updated": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
                "updated_by": message.from_user.username or message.from_user.first_name
            })
            
            # Сохраняем в файл
            save_json_data(AD_TEMPLATES_FILE, ad_templates)
            
            category_name = AD_CATEGORIES.get(new_category, {}).get("name", "Неизвестно")
            
            bot.reply_to(message, 
                        f"✅ **Объявление обновлено!**\n\n"
                        f"**Новая категория:** {category_name}\n"
                        f"**Новый текст:**\n{new_text}", 
                        parse_mode="Markdown")
            
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при сохранении: {str(e)}")
        
        # Очищаем состояние
        del user_states[user_id]
    
    def delete_ad(bot, chat_id: int, brand: str, city: str, ad_type: str, index: int):
        """Удаляет объявление."""
        try:
            ad = ad_templates[brand][city][ad_type][index]
            del ad_templates[brand][city][ad_type][index]
            
            # Если список стал пустым, удаляем его
            if not ad_templates[brand][city][ad_type]:
                del ad_templates[brand][city][ad_type]
                
            # Если город стал пустым, удаляем его
            if not ad_templates[brand][city]:
                del ad_templates[brand][city]
                
            # Если бренд стал пустым, удаляем его
            if not ad_templates[brand]:
                del ad_templates[brand]
            
            # Сохраняем в файл
            save_json_data(AD_TEMPLATES_FILE, ad_templates)
            
            preview = ad["text"][:50] + "..." if len(ad["text"]) > 50 else ad["text"]
            bot.send_message(chat_id, f"🗑️ **Объявление удалено:**\n{preview}", parse_mode="Markdown")
            
        except (KeyError, IndexError):
            bot.send_message(chat_id, "❌ Объявление не найдено или уже удалено.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка при удалении: {str(e)}")

    # ========================================
    #   ОБРАБОТЧИКИ КОЛЛБЕКОВ ДЛЯ РЕКЛАМЫ
    # ========================================
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("ads_"))
    def handle_ads_callbacks(call):
        """Обработчик всех коллбеков новой системы рекламы."""
        try:
            if call.data == "ads_add_new":
                start_add_ad_wizard(bot, call.message.chat.id, call.from_user.id)
                bot.answer_callback_query(call.id, "Начинаем добавление рекламы")
                
            elif call.data == "ads_view_categories":
                show_ad_categories_menu(bot, call.message.chat.id)
                bot.answer_callback_query(call.id)
                
            elif call.data.startswith("ads_category_"):
                category_id = call.data.replace("ads_category_", "")
                show_ads_in_category(bot, call.message.chat.id, category_id)
                bot.answer_callback_query(call.id)
                
            elif call.data == "ads_search":
                start_ads_search(bot, call.message.chat.id, call.from_user.id)
                bot.answer_callback_query(call.id, "Начинаем поиск")
                
            elif call.data == "ads_stats":
                show_ads_statistics(bot, call.message.chat.id)
                bot.answer_callback_query(call.id)
                
            elif call.data == "ads_back_main":
                command_ads_new(call.message)
                bot.answer_callback_query(call.id)
                
            elif call.data.startswith("ads_view_"):
                # Обработка просмотра конкретного объявления
                parts = call.data.replace("ads_view_", "").split("_")
                if len(parts) >= 4:
                    brand, city, ad_type, index = parts[0], parts[1], parts[2], int(parts[3])
                    show_single_ad(bot, call.message.chat.id, brand, city, ad_type, index)
                bot.answer_callback_query(call.id)
                
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")
    
    def start_ads_search(bot, chat_id: int, user_id: int):
        """Начинает поиск рекламы по ключевым словам."""
        user_states[user_id] = {
            "state": "ads_searching", 
            "chat_id": chat_id
        }
        
        text = ("🔍 **Поиск рекламы**\n\n"
                "Введите ключевые слова для поиска по всем объявлениям.\n"
                "*Пример:* `скидка`, `караоке`, `меню`\n\n"
                "Или отправьте /cancel для отмены.")
        
        msg = bot.send_message(chat_id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_ads_search, bot)
    
    def process_ads_search(message: types.Message, bot):
        """Обработка поискового запроса."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if not state or state.get("state") != "ads_searching":
            return
        
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Поиск отменен.")
        
        search_query = message.text.lower()
        found_ads = []
        
        # Поиск по всем объявлениям
        for brand, brand_data in ad_templates.items():
            for city, city_data in brand_data.items():
                for ad_type, ads_list in city_data.items():
                    for i, ad in enumerate(ads_list):
                        if search_query in ad.get("text", "").lower():
                            found_ads.append({
                                "brand": brand,
                                "city": city,
                                "type": ad_type,
                                "index": i,
                                "text": ad.get("text", ""),
                                "category": ad.get("category", "general")
                            })
        
        if not found_ads:
            bot.reply_to(message, f"🔍 По запросу **\"{search_query}\"** ничего не найдено.", parse_mode="Markdown")
        else:
            text = f"🔍 **Результаты поиска по запросу \"{search_query}\"**\n\nНайдено: {len(found_ads)} объявлений\n\n"
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, ad in enumerate(found_ads[:10]):  # Показываем первые 10
                category_name = AD_CATEGORIES.get(ad["category"], {}).get("name", "")
                preview = ad["text"][:50] + "..." if len(ad["text"]) > 50 else ad["text"]
                markup.add(types.InlineKeyboardButton(
                    f"{category_name} {ad['brand']}/{ad['city']} - {preview}",
                    callback_data=f"ads_view_{ad['brand']}_{ad['city']}_{ad['type']}_{ad['index']}"
                ))
            
            if len(found_ads) > 10:
                text += f"*Показаны первые 10 из {len(found_ads)} результатов*"
            
            bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)
        
        # Очищаем состояние
        if user_id in user_states:
            del user_states[user_id]
    
    def show_ads_statistics(bot, chat_id: int):
        """Показывает статистику по рекламе."""
        total_ads = 0
        categories_stats = {cat_id: 0 for cat_id in AD_CATEGORIES.keys()}
        brands_stats = {}
        
        # Подсчитываем статистику
        for brand, brand_data in ad_templates.items():
            brand_count = 0
            for city, city_data in brand_data.items():
                for ad_type, ads_list in city_data.items():
                    for ad in ads_list:
                        total_ads += 1
                        brand_count += 1
                        category = ad.get("category", "general")
                        if category in categories_stats:
                            categories_stats[category] += 1
            brands_stats[brand] = brand_count
        
        # Формируем текст статистики
        text = f"📊 **Статистика рекламы**\n\n**Всего объявлений:** {total_ads}\n\n"
        
        text += "**По категориям:**\n"
        for cat_id, count in categories_stats.items():
            if count > 0:
                cat_name = AD_CATEGORIES[cat_id]["name"]
                text += f"  {cat_name}: {count}\n"
        
        text += "\n**По брендам:**\n"
        for brand, count in sorted(brands_stats.items(), key=lambda x: x[1], reverse=True):
            text += f"  {brand.upper()}: {count}\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_back_main"))
        
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    
    def show_single_ad(bot, chat_id: int, brand: str, city: str, ad_type: str, index: int):
        """Показывает детали конкретного объявления."""
        try:
            ad = ad_templates[brand][city][ad_type][index]
            category_name = AD_CATEGORIES.get(ad.get("category", "general"), {}).get("name", "Неизвестно")
            
            text = (f"📝 **Детали объявления**\n\n"
                   f"**Бренд:** {brand.upper()}\n"
                   f"**Город:** {city.capitalize()}\n"
                   f"**Тип:** {ad_type.capitalize()}\n"
                   f"**Категория:** {category_name}\n"
                   f"**Создано:** {ad.get('created', 'Неизвестно')}\n"
                   f"**Автор:** {ad.get('created_by', 'Неизвестно')}\n\n"
                   f"**Текст:**\n{ad.get('text', '')}")
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✏️ Редактировать", 
                                         callback_data=f"ads_edit_{brand}_{city}_{ad_type}_{index}"),
                types.InlineKeyboardButton("🗑️ Удалить", 
                                         callback_data=f"ads_delete_{brand}_{city}_{ad_type}_{index}")
            )
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="ads_view_categories"))
            
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
            
        except (KeyError, IndexError):
            bot.send_message(chat_id, "❌ Объявление не найдено или было удалено.")
