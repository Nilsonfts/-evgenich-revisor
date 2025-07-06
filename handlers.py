# handlers.py
import logging
import os
import datetime
import random
import pytz
import threading
import time
import pandas as pd
from telebot import types
from collections import Counter

# Импорты из наших собственных модулей
from config import *
from state import *
from g_sheets import get_sheet
from utils import (
    is_admin, admin_required, get_username, get_chat_title,
    init_user_data, init_shift_data, handle_user_return,
    save_history_event, save_json_data, generate_detailed_report
)
from scheduler import send_end_of_shift_report_for_chat
from models import UserData # Импортируем нашу модель

try:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None
except ImportError:
    client = None

pending_transfers = {}

def register_handlers(bot):
    """Регистрирует все обработчики сообщений и колбэков для бота."""

    def analyze_voice_thread(audio_path: str, user_data: UserData, chat_id: int):
        """Анализирует аудио в отдельном потоке, чтобы не блокировать бота."""
        if not client or not ad_templates:
            if os.path.exists(audio_path): os.remove(audio_path)
            return

        chat_config = chat_configs.get(str(chat_id), {})
        brand, city = chat_config.get("brand"), chat_config.get("city")
        if not brand or not city:
            if os.path.exists(audio_path): os.remove(audio_path)
            return

        templates_for_location = ad_templates.get(brand, {}).get(city)
        if not templates_for_location:
            if os.path.exists(audio_path): os.remove(audio_path)
            return

        try:
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            
            recognized_text = transcript.text
            if not recognized_text.strip(): return

            system_prompt = "Ты — ассистент, который находит в тексте диктора упоминания рекламных шаблонов из списка. В ответ верни названия ВСЕХ подходящих шаблонов, каждое с новой строки. Если совпадений нет, верни 'None'."
            ad_list_for_prompt = "\n".join([f"- {name}: '{text}'" for name, text in templates_for_location.items()])
            user_prompt = f"Текст диктора: '{recognized_text}'.\n\nСписок шаблонов:\n{ad_list_for_prompt}\n\nКакие шаблоны были упомянуты?"

            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0
            )
            analysis_result_text = completion.choices[0].message.content.strip()

            if analysis_result_text != 'None':
                found_templates = [line.strip() for line in analysis_result_text.splitlines() if line.strip() in templates_for_location]
                if found_templates:
                    user_data.recognized_ads.extend(found_templates)
                    logging.info(f"GPT ({chat_id}) определил совпадения: {found_templates}")
        except Exception as e:
            logging.error(f"Ошибка OpenAI ({chat_id}): {e}")
            try:
                if BOSS_ID: bot.send_message(BOSS_ID, f"❗️ Ошибка анализа речи OpenAI в чате {get_chat_title(bot, chat_id)}:\n`{e}`")
            except Exception as send_e:
                logging.error(f"Не удалось отправить ЛС об ошибке: {send_e}")
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    @bot.message_handler(content_types=['voice'])
    def handle_voice_message(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: return

        user_id = message.from_user.id
        username = get_username(message.from_user)
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

        if chat_id not in chat_data: init_shift_data(chat_id)
        
        shift = chat_data[chat_id]
        if user_id not in shift.users:
            shift.users[user_id] = init_user_data(user_id, username)

        is_new_main = False
        if shift.main_id is None:
            shift.main_id = user_id
            shift.main_username = username
            is_new_main = True

        if shift.main_id == user_id:
            if is_new_main:
                phrase = random.choice(soviet_phrases.get("system_messages", {}).get('first_voice_new_main', ["👑 {username} становится главным, записав первое ГС!"]))
                bot.send_message(chat_id, phrase.format(username=username))
                save_history_event(chat_id, user_id, username, "Стал главным (первое ГС)")

            user_data = shift.users[user_id]
            
            if not is_new_main and user_data.last_voice_time:
                last_voice_time = datetime.datetime.fromisoformat(user_data.last_voice_time)
                time_since_last = (now_moscow - last_voice_time).total_seconds()
                if time_since_last < VOICE_COOLDOWN_SECONDS:
                    remaining = int(VOICE_COOLDOWN_SECONDS - time_since_last)
                    phrase = random.choice(soviet_phrases.get("system_messages", {}).get('voice_cooldown', ["Слишком часто! Пауза {remaining} сек."]))
                    bot.reply_to(message, phrase.format(remaining=remaining), disable_notification=True)
                    return

            if message.voice.duration < VOICE_MIN_DURATION_SECONDS:
                bot.reply_to(message, f"*{random.choice(soviet_phrases.get('too_short', ['Коротко']))}* ({message.voice.duration} сек)")
                return

            bot.send_message(chat_id, f"*{random.choice(soviet_phrases.get('accept', ['Принято']))}*", reply_to_message_id=message.message_id)

            if user_data.last_voice_time:
                delta_minutes = (now_moscow - datetime.datetime.fromisoformat(user_data.last_voice_time)).total_seconds() / 60
                user_data.voice_deltas.append(delta_minutes)

            user_data.count += 1
            user_data.last_voice_time = now_moscow.isoformat()
            user_data.voice_durations.append(message.voice.duration)
            user_data.last_activity_reminder_time = None

            if client:
                try:
                    file_info = bot.get_file(message.voice.file_id)
                    downloaded_file = bot.download_file(file_info.file_path)
                    file_path = f"voice_{message.message_id}.ogg"
                    with open(file_path, 'wb') as new_file:
                        new_file.write(downloaded_file)
                    threading.Thread(target=analyze_voice_thread, args=(file_path, user_data, chat_id)).start()
                except Exception as e:
                    logging.error(f"Ошибка при скачивании аудиофайла: {e}")

    @bot.message_handler(func=lambda m: m.text and any(word in m.text.lower().split() for word in BREAK_KEYWORDS))
    def handle_break_request(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        if not shift or shift.main_id != user_id: return
        
        user_data = shift.users[user_id]
        
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
                bot.send_message(chat_id, phrase)
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
        
        phrase_template = random.choice(soviet_phrases.get("system_messages", {}).get('shift_transfer_offer', ["."]))
        text = phrase_template.format(from_username=from_username, to_username=to_username)
        
        sent_message = bot.send_message(chat_id, text, reply_markup=markup)
        
        timer = threading.Timer(300, cancel_transfer, args=[chat_id])
        timer.start()
        
        pending_transfers[chat_id] = {
            'from_id': from_user.id, 'from_username': from_username,
            'to_id': to_user.id, 'to_username': to_username,
            'message_id': sent_message.message_id, 'timer': timer
        }

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
        
        shift = chat_data[chat_id]
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

    @bot.message_handler(commands=['start', 'старт'])
    def handle_start(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: 
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('group_only_command', ["Эта команда работает только в групповом чате."]))
            return bot.reply_to(message, phrase)
            
        from_user = message.from_user
        username = get_username(from_user)
        
        if chat_id not in chat_data: init_shift_data(chat_id)
        
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

    @bot.message_handler(commands=['промежуточный', 'check'])
    def handle_check(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        shift = chat_data.get(chat_id)
        
        if not shift or not shift.main_id:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_not_started', ["Смена в этом чате еще не началась."]))
            return bot.reply_to(message, phrase)
            
        if user_id != shift.main_id:
            main_username = shift.main_username
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('only_for_main_user', ["Эту команду может использовать только текущий главный на смене: {main_username}."]))
            return bot.reply_to(message, phrase.format(main_username=main_username))
            
        main_user_data = shift.users[shift.main_id]
        shift_goal = shift.shift_goal
        plan_percent = (main_user_data.count / shift_goal * 100) if shift_goal > 0 else 0
        report_lines = [
            f"📋 *Промежуточный отчет для вас* ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
            f"🗣️ **Голосовых:** {main_user_data.count} из {shift_goal} ({plan_percent:.0f}%)",
            f"☕ **Перерывов:** {main_user_data.breaks_count}",
            f"⏳ **Опозданий с перерыва:** {main_user_data.late_returns}"
        ]
        ad_counts = Counter(main_user_data.recognized_ads)
        if ad_counts:
            report_lines.append("\n**📝 Анализ контента:**")
            for ad, count in ad_counts.items():
                report_lines.append(f"✔️ {ad} (x{count})")
        bot.reply_to(message, "\n".join(report_lines), parse_mode="Markdown")

    @bot.message_handler(commands=['сводка'])
    def my_total_stats(message: types.Message):
        if not pd: return bot.reply_to(message, "Модуль для анализа данных (pandas) не загружен.")
        user_id = message.from_user.id
        username = get_username(message.from_user)
        bot.reply_to(message, f"📊 Собираю вашу общую статистику из Google Таблицы, {username}. Минутку...")
        worksheet = get_sheet()
        if not worksheet: return bot.send_message(message.chat.id, "Не удалось подключиться к Google Таблице.")
        try:
            df = pd.DataFrame(worksheet.get_all_records())
            if df.empty or 'ID Ведущего' not in df.columns: return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")
            df['ID Ведущего'] = pd.to_numeric(df['ID Ведущего'], errors='coerce')
            user_df = df[df['ID Ведущего'] == user_id].copy()
            if user_df.empty: return bot.send_message(message.chat.id, f"{username}, не найдено ваших смен в общей статистике.")
            numeric_cols = ['Голосовых (шт)', 'Перерывов (шт)', 'Опозданий (шт)']
            for col in numeric_cols: user_df[col] = pd.to_numeric(user_df[col], errors='coerce').fillna(0)
            total_shifts = len(user_df)
            total_voices = user_df['Голосовых (шт)'].sum()
            total_breaks = user_df['Перерывов (шт)'].sum()
            total_lates = user_df['Опозданий (шт)'].sum()
            report_text = (
                f"⭐️ **Общая статистика для {username}** ⭐️\n\n"
                f"👑 **Всего смен отработано:** {total_shifts}\n"
                f"🗣️ **Всего голосовых записано:** {int(total_voices)}\n"
                f"☕️ **Всего перерывов:** {int(total_breaks)}\n"
                f"⏳ **Всего опозданий с перерыва:** {int(total_lates)}"
            )
            bot.send_message(message.chat.id, report_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка анализа Google Sheets для /сводка: {e}")
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('generic_error', ["Произошла ошибка при выполнении команды."]))
            bot.send_message(message.chat.id, phrase)

    @bot.message_handler(commands=['help'])
    def handle_help(message: types.Message):
        help_text_lines = [
            "📘 **Основные команды для ведущего:**\n",
            "`/start` или `/старт`",
            "Занять смену, если она свободна.\n",
            "`/промежуточный` или `/check`",
            "Показать свой личный отчет по текущей смене.\n",
            "`/сводка`",
            "Посмотреть свою общую статистику за все время.\n",
            "`/передать`",
            "Передать смену другому (нужно ответить на его сообщение).\n",
            "☕️ Для перерыва просто напишите в чат `перерыв`, `обед` или `отдых`.",
            "✅ Для возвращения — `вернулся`, `на месте`."
        ]
        bot.reply_to(message, "\n".join(help_text_lines), parse_mode="Markdown")

    @bot.message_handler(commands=['admin'])
    @admin_required(bot)
    def handle_admin_panel(message: types.Message):
        user_id = message.from_user.id
        panel_text = [
            "**⚜️ Панель работы администратора ⚜️**\n",
            "`/status` — 📊 Статус текущей смены",
            "`/rating` — 📈 Общий рейтинг сотрудников",
            "`/ads` — 📝 Управление рекламными шаблонами",
            "`/problems` — 🚨 Поиск проблемных зон",
            "`/restart` — 🔄 Перезапустить смену",
            "`/report` — ➡️ Отчет досрочно",
            "`/log` — 📜 Выгрузить лог смены",
            "`/time` — ⏱️ Изменить тайм-аут активности",
            "`/setup_wizard` — 🧙‍♂️ Мастер настройки чата",
        ]
        if user_id == BOSS_ID:
             panel_text.append("`/broadcast` — 📢 Рассылка (BOSS)")
        
        panel_text.append("\n*Для подробной расшифровки введите /adminhelp*")
        bot.reply_to(message, "\n".join(panel_text), parse_mode="Markdown")

    @bot.message_handler(commands=['adminhelp'])
    @admin_required(bot)
    def handle_admin_help(message: types.Message):
        help_text = [
            "**🛠️ Расширенная справка для администратора**\n"
            "====================\n"
            "**АНАЛИТИКА И ОТЧЕТЫ:**\n",
            "`/status` — 📊 Показывает полный статус *текущей смены*: кто на смене, сколько сделано, статистика по паузам и т.д.",
            "`/rating` — 📈 Выводит общий рейтинг всех ведущих на основе данных из Google Таблицы.",
            "`/problems` — 🚨 Анализирует данные из Google Таблицы и подсвечивает смены с низкой эффективностью, опозданиями или слишком долгими паузами.",
            "`/log` — 📜 Выгружает текстовый файл с историей всех ключевых событий за *текущую* смену.",
            "\n**УПРАВЛЕНИЕ СМЕНОЙ:**\n",
            "`/restart` — 🔄 Принудительно сбрасывает *текущую* смену. Потребуется новый `/start` для начала.",
            "`/report` — ➡️ Завершает смену досрочно и отправляет финальный отчет.",
            "\n**УПРАВЛЕНИЕ КОНТЕНТОМ И НАСТРОЙКИ:**\n",
            "`/ads` — 📝 Открывает интерактивное меню для управления рекламными шаблонами (просмотр, добавление, удаление).",
            "`/time [минуты]` — ⏱️ Устанавливает, через сколько минут бездействия бот начнет напоминать ведущему. *Пример: `/time 25`*",
            "`/setup_wizard` — 🧙‍♂️ Запускает удобный пошаговый мастер для полной настройки чата (рекомендуется).",
        ]
        if message.from_user.id == BOSS_ID:
            help_text.append("`/broadcast` — 📢 Отправляет сообщение во все чаты, где работает бот (только для BOSS).")
        
        bot.reply_to(message, "\n".join(help_text), parse_mode="Markdown")

    @bot.message_handler(commands=['time'])
    @admin_required(bot)
    def command_set_timeout(message: types.Message):
        chat_id = message.chat.id
        try:
            args = message.text.split()
            if len(args) != 2:
                raise ValueError("Неверное количество аргументов.")
            
            new_timeout = int(args[1])
            if new_timeout <= 0:
                raise ValueError("Значение должно быть положительным.")

            if str(chat_id) not in chat_configs:
                chat_configs[str(chat_id)] = {}
            
            chat_configs[str(chat_id)]['voice_timeout'] = new_timeout
            
            if save_json_data(CHAT_CONFIG_FILE, chat_configs):
                bot.reply_to(message, f"✅ **Успешно!**\nТеперь напоминания об отсутствии голосовых будут приходить через *{new_timeout} минут* бездействия в этом чате.")
                logging.info(f"Администратор {message.from_user.id} изменил тайм-аут для чата {chat_id} на {new_timeout} минут.")
            else:
                bot.reply_to(message, "❌ **Ошибка!**\nНе удалось сохранить новую настройку. Проверьте логи бота.")

        except (ValueError, IndexError):
            default_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)
            bot.reply_to(message, f"**Неверный формат команды.**\n\nИспользуйте: `/time [минуты]`\n*Пример:* `/time 25`\n\nТекущее значение для этого чата: *{default_timeout} минут*.")


    @bot.message_handler(commands=['status'])
    @admin_required(bot)
    def command_status(message: types.Message):
        chat_id = message.chat.id
        shift = chat_data.get(chat_id)
        if not shift or not shift.main_id:
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('shift_not_started', ["Смена в этом чате еще не началась."]))
            return bot.send_message(chat_id, phrase)
        
        report_lines = generate_detailed_report(chat_id, shift)
        report_text = "\n".join(report_lines)
        bot.send_message(chat_id, report_text, parse_mode="Markdown")
    
    @bot.message_handler(commands=['rating'])
    @admin_required(bot)
    def command_rating(message: types.Message):
        chat_id = message.chat.id
        if not pd: return bot.send_message(chat_id, "Модуль для анализа данных (pandas) не загружен.")
        bot.send_message(chat_id, "📊 Анализирую общую статистику из Google Таблицы...")
        worksheet = get_sheet()
        if not worksheet: return bot.send_message(chat_id, "Не удалось подключиться к Google Таблице.")
        try:
            df = pd.DataFrame(worksheet.get_all_records())
            if df.empty or 'Тег Ведущего' not in df.columns: return bot.send_message(chat_id, "В таблице пока нет данных для анализа.")
            numeric_cols = ['Голосовых (шт)', 'Опозданий (шт)']
            for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=numeric_cols, inplace=True)
            summary = df.groupby('Тег Ведущего').agg(
                total_shifts=('Дата', 'count'),
                total_voices=('Голосовых (шт)', 'sum'),
                total_lates=('Опозданий (шт)', 'sum')
            ).reset_index()
            summary['avg_voices'] = summary['total_voices'] / summary['total_shifts']
            summary['lateness_percent'] = (summary['total_lates'] / summary['total_shifts']) * 100
            summary = summary.sort_values(by='avg_voices', ascending=False).reset_index(drop=True)
            report_lines = ["📊 **Общая сводка по всем сотрудникам**\n_(На основе данных из Google Sheets)_\n"]
            medals = {0: "🥇", 1: "🥈", 2: "🥉"}
            for i, row in summary.iterrows():
                rank_icon = medals.get(i, f" {i+1}.")
                report_lines.append(f"*{rank_icon}* {row['Тег Ведущего']} — *Ср. ГС:* `{row['avg_voices']:.1f}` | *Опоздания:* `{row['lateness_percent']:.0f}%` | *Смен:* `{row['total_shifts']}`")
            bot.send_message(chat_id, "\n".join(report_lines), parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка анализа Google Sheets для /rating: {e}")
            phrase = random.choice(soviet_phrases.get("system_messages", {}).get('generic_error', ["Произошла ошибка при выполнении команды."]))
            bot.send_message(chat_id, phrase)
        
    @bot.message_handler(commands=['problems'])
    @admin_required(bot)
    def command_problems(message: types.Message):
        chat_id = message.chat.id
        if not pd: return bot.send_message(chat_id, "Модуль для анализа данных (pandas) не загружен.")
        bot.send_message(chat_id, "🚨 Ищу проблемные зоны в Google Таблице...")
        worksheet = get_sheet()
        if not worksheet: return bot.send_message(chat_id, "Не удалось подключиться к Google Таблице.")
        try:
            df = pd.DataFrame(worksheet.get_all_records())
            if df.empty: return bot.send_message(chat_id, "В таблице нет данных.")
            
            chat_timeout = chat_configs.get(str(chat_id), {}).get('voice_timeout', VOICE_TIMEOUT_MINUTES)
            
            numeric_cols = ['Выполнение (%)', 'Опозданий (шт)', 'Макс. пауза (мин)']
            for col in numeric_cols:
                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=numeric_cols, inplace=True)
            low_perf = df[df['Выполнение (%)'] < 80]
            latecomers = df[df['Опозданий (шт)'] > 0]
            long_pauses = df[df['Макс. пауза (мин)'] > (chat_timeout * 1.5)]
            report_lines = ["🚨 **Анализ проблемных зон**\n"]
            if not low_perf.empty:
                report_lines.append("*📉 Низкое выполнение плана (<80%):*")
                for _, row in low_perf.sort_values(by='Дата', ascending=False).iterrows():
                    report_lines.append(f" - {row.get('Дата', 'N/A')} {row.get('Тег Ведущего', 'N
