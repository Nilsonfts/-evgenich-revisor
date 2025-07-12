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
    "menu": {"name": "🍽️ Меню", "keywords": ["меню", "блюдо", "кухня", "еда", "напиток", "акция", "скидка"]},
    "events": {"name": "🎉 События", "keywords": ["вечеринка", "корпоратив", "день рождения", "праздник", "мероприятие"]},
    "promo": {"name": "🎁 Акции", "keywords": ["скидка", "акция", "промо", "бесплатно", "подарок", "бонус"]},
    "karaoke": {"name": "🎤 Караоке", "keywords": ["караоке", "песня", "микрофон", "сцена", "пение"]},
    "booking": {"name": "📅 Бронь", "keywords": ["бронирование", "столик", "резерв", "место", "заказ"]},
    "general": {"name": "📢 Общее", "keywords": ["работаем", "открыты", "график", "контакты", "адрес"]}
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
        """Простая настройка концепции чата."""
        chat_id = message.chat.id
        
        # Создаем клавиатуру с концепциями
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("РВБ", callback_data="wizard_concept_РВБ"))
        markup.add(types.InlineKeyboardButton("ЕВГЕНИЧ", callback_data="wizard_concept_ЕВГЕНИЧ"))
        markup.add(types.InlineKeyboardButton("НЕБАР", callback_data="wizard_concept_НЕБАР"))
        markup.add(types.InlineKeyboardButton("СПЛЕТНИ", callback_data="wizard_concept_СПЛЕТНИ"))
        markup.add(types.InlineKeyboardButton("ОРБИТА", callback_data="wizard_concept_ОРБИТА"))
        
        text = ("🧙‍♂️ **Мастер настройки чата**\n\n"
                "Выберите концепцию для этого чата:")
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("wizard_concept_"))
    def handle_wizard_concept_callback(call):
        """Обработка выбора концепции."""
        concept_id = call.data.replace("wizard_concept_", "")
        chat_id = str(call.message.chat.id)
        
        # Простое сохранение концепции в конфиг чата
        if chat_id not in chat_configs:
            chat_configs[chat_id] = {}
        
        chat_configs[chat_id]["concept"] = concept_id
        save_json_data(CHAT_CONFIG_FILE, chat_configs)
        
        text = f"✅ **Концепция установлена: {concept_id}**\n\nЧат настроен и готов к работе!"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id, f"Установлена концепция: {concept_id}")
        
        logging.info(f"Chat {chat_id} configured with concept: {concept_id}")
    
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
