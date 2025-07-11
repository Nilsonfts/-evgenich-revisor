# handlers.py
import telebot
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
from database import db  # Импортируем базу данных

try:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None
except ImportError:
    client = None

pending_transfers = {}

def register_handlers(bot):
    """Регистрирует все обработчики сообщений и колбэков для бота."""
    
    # Middleware для проверки состояния бота
    @bot.middleware_handler(update_types=['message'])
    def check_bot_enabled(bot_instance, message):
        """Проверяет, включен ли бот для данного чата."""
        # Исключаем команды управления ботом и приватные чаты
        if (message.chat.id > 0 or 
            (message.text and any(cmd in message.text for cmd in ['/bot_on', '/включить', '/bot_status', '/admin']))):
            return
        
        if not db.is_bot_enabled(message.chat.id):
            # Бот выключен, игнорируем сообщение
            return False

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

    # Обработчик /передать перенесен в handlers/shift.py для избежания дублирования

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

    # Обработчик /start перенесен в handlers/shift.py для избежания дублирования

    # Обработчик /промежуточный перенесен в handlers/user.py для избежания дублирования

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
                    report_lines.append(f" - {row.get('Дата', 'N/A')} {row.get('Тег Ведущего', 'N/A')}: *{row['Выполнение (%)']:.0f}%*")
            if not latecomers.empty:
                report_lines.append("\n*⏳ Опоздания с перерывов:*")
                for _, row in latecomers.sort_values(by='Дата', ascending=False).iterrows():
                    report_lines.append(f" - {row.get('Дата', 'N/A')} {row.get('Тег Ведущего', 'N/A')}: *{int(row['Опозданий (шт)'])}* раз(а)")
            if not long_pauses.empty:
                report_lines.append(f"\n*⏱️ Слишком долгие паузы (дольше {int(chat_timeout*1.5)} мин):*")
                for _, row in long_pauses.sort_values(by='Дата', ascending=False).iterrows():
                    report_lines.append(f" - {row.get('Дата', 'N/A')} {row.get('Тег Ведущего', 'N/A')}: макс. пауза *{row['Макс. пауза (мин)']:.0f} мин*")
            if len(report_lines) == 1:
                bot.send_message(chat_id, "✅ Проблемных зон по основным критериям не найдено. Отличная работа!")
            else:
                bot.send_message(chat_id, "\n".join(report_lines), parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка поиска проблемных зон: {e}")
            bot.send_message(chat_id, f"Произошла ошибка при анализе: {e}")
        
    @bot.message_handler(commands=['restart'])
    @admin_required(bot)
    def command_restart(message: types.Message):
        chat_id = message.chat.id
        if chat_id in chat_data and chat_data[chat_id].main_id is not None:
            init_shift_data(chat_id)
            bot.send_message(chat_id, "🔄 Смена перезапущена администратором. Текущий главный и план сброшены.")
            save_history_event(chat_id, message.from_user.id, get_username(message.from_user), "Перезапустил смену")
        else:
            bot.send_message(chat_id, "Активной смены в этом чате и так не было.")

    @bot.message_handler(commands=['report'])
    @admin_required(bot)
    def command_report(message: types.Message):
        bot.send_message(message.chat.id, "⏳ Формирую финальный отчет досрочно по команде администратора...")
        send_end_of_shift_report_for_chat(bot, message.chat.id)

    @bot.message_handler(commands=['log'])
    @admin_required(bot)
    def command_log(message: types.Message):
        chat_id = message.chat.id
        history = user_history.get(chat_id)
        if not history:
            return bot.send_message(chat_id, "История событий для текущей смены пуста.")
        try:
            filename = f"history_{chat_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"История событий для чата: {get_chat_title(bot, chat_id)}\n" + "="*40 + "\n" + "\n".join(history))
            with open(filename, 'rb') as f_rb:
                bot.send_document(chat_id, f_rb, caption="Лог событий текущей смены.")
            os.remove(filename)
        except Exception as e:
            logging.error(f"Ошибка при выгрузке истории: {e}")
            bot.send_message(chat_id, "Произошла ошибка при создании файла истории.")
            
    # ... (остальные админские команды без изменений)

    # (Код для broadcast, setup_wizard и ads остается таким же, как был)
    @bot.message_handler(commands=['broadcast'])
    @admin_required(bot)
    def command_broadcast(message: types.Message):
        if message.from_user.id != BOSS_ID:
            return bot.send_message(message.chat.id, "⛔️ Эта команда доступна только для BOSS.")
        msg = bot.send_message(message.chat.id, "Введите текст для массовой рассылки всем чатам. Для отмены введите /cancel.")
        bot.register_next_step_handler(msg, process_broadcast_text)
        
    def process_broadcast_text(message: types.Message):
        if message.text == '/cancel':
            return bot.send_message(message.chat.id, "Рассылка отменена.")
        if message.from_user.id != BOSS_ID: return
        text_to_send = message.text
        if not text_to_send: return bot.reply_to(message, "Текст рассылки не может быть пустым.")
        sent_count = 0
        total_chats = len(list(chat_configs.keys()))
        bot.send_message(message.chat.id, f"Начинаю рассылку в {total_chats} чатов...")
        for chat_id_str in chat_configs.keys():
            try:
                bot.send_message(int(chat_id_str), f"❗️ **Важное объявление от руководства:**\n\n{text_to_send}", parse_mode="Markdown")
                sent_count += 1
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Не удалось отправить рассылку в чат {chat_id_str}: {e}")
        bot.send_message(message.chat.id, f"✅ Рассылка успешно отправлена в {sent_count} из {total_chats} чатов.")

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
        bot.register_next_step_handler(msg, process_wizard_brand_city)

    def process_wizard_brand_city(message: types.Message):
        """Шаг 1: Обработка бренда и города."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if state.get("state") != "wizard_awaiting_brand_city": return
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Настройка отменена.")

        try:
            brand, city = message.text.split(maxsplit=2)
            state["data"]["brand"] = brand.lower()
            state["data"]["city"] = city.lower()
            
            state["state"] = "wizard_awaiting_timezone"
            text = ("✅ **Шаг 2 из 4:** Отлично! Теперь укажите **часовой пояс**.\n"
                    "Введите смещение от Москвы. *Пример:* `+3` или `-1`")
            msg = bot.reply_to(message, text, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_timezone)
        except ValueError:
            msg = bot.reply_to(message, "❌ **Ошибка.** Пожалуйста, введите два слова: бренд и город. *Пример:* `my-brand moscow`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_brand_city)
            
    def process_wizard_timezone(message: types.Message):
        """Шаг 2: Обработка часового пояса."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if state.get("state") != "wizard_awaiting_timezone": return
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.reply_to(message, "Настройка отменена.")
            
        offset = message.text.strip()
        tz_name = TIMEZONE_MAP.get(offset)
        if not tz_name:
            msg = bot.reply_to(message, f"❌ **Ошибка.** Неверный формат смещения. Доступные варианты: {list(TIMEZONE_MAP.keys())}\nПопробуйте еще раз.", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_timezone)
            return
            
        state["data"]["timezone"] = tz_name
        
        state["state"] = "wizard_awaiting_timing"
        text = ("✅ **Шаг 3 из 4:** Часовой пояс установлен! Теперь задайте **график смены**.\n"
                "Введите время начала и конца. *Пример:* `19:00 04:00`")
        msg = bot.reply_to(message, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_wizard_timing)

    def process_wizard_timing(message: types.Message):
        """Шаг 3: Обработка времени смены."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if state.get("state") != "wizard_awaiting_timing": return
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
            bot.register_next_step_handler(msg, process_wizard_goal)
        except (ValueError, IndexError):
            msg = bot.reply_to(message, "❌ **Ошибка.** Неверный формат. Введите два времени через пробел. *Пример:* `19:00 04:00`", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_wizard_timing)

    def process_wizard_goal(message: types.Message):
        """Шаг 4: Обработка цели и завершение."""
        user_id = message.from_user.id
        state = user_states.get(user_id, {})
        if state.get("state") != "wizard_awaiting_goal": return
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
            bot.register_next_step_handler(msg, process_wizard_goal)
        finally:
            if user_id in user_states:
                del user_states[user_id]
    
    @bot.message_handler(commands=['ads'])
    @admin_required(bot)
    def command_ads(message: types.Message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        brands = list(ad_templates.keys())
        for brand in brands:
            markup.add(types.InlineKeyboardButton(brand.upper(), callback_data=f"ad_brand_{brand}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить новый бренд", callback_data="ad_addbrand_form"))
        bot.send_message(message.chat.id, "📝 Выберите бренд для управления рекламой:", reply_markup=markup)
    
    def show_ad_cities_menu(chat_id: int, brand: str):
        markup = types.InlineKeyboardMarkup(row_width=2)
        cities = list(ad_templates.get(brand, {}).keys())
        for city in cities:
            markup.add(types.InlineKeyboardButton(city.capitalize(), callback_data=f"ad_city_{brand}_{city}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить новый город", callback_data=f"ad_addcity_form_{brand}"))
        markup.add(types.InlineKeyboardButton("« Назад к брендам", callback_data="ad_backtobrand"))
        bot.send_message(chat_id, f"Бренд: *{brand.upper()}*\nВыберите город:", reply_markup=markup, parse_mode="Markdown")
    
    def show_ad_actions_menu(chat_id: int, brand: str, city: str):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👁️‍🗨️ Просмотреть шаблоны", callback_data=f"ad_view_{brand}_{city}"),
            types.InlineKeyboardButton("➕ Добавить шаблон", callback_data=f"ad_addform_{brand}_{city}"),
            types.InlineKeyboardButton("➖ Удалить шаблон", callback_data=f"ad_delform_{brand}_{city}"),
            types.InlineKeyboardButton("« Назад к городам", callback_data=f"ad_backtocity_{brand}")
        )
        bot.send_message(chat_id, f"Бренд: *{brand.upper()}* / Город: *{city.capitalize()}*\nВыберите действие:", reply_markup=markup, parse_mode="Markdown")

    def show_templates_for_deletion(chat_id: int, brand: str, city: str):
        templates = ad_templates.get(brand, {}).get(city, {})
        if not templates:
            bot.send_message(chat_id, "Здесь нет шаблонов для удаления.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for tpl_key in templates.keys():
            markup.add(types.InlineKeyboardButton(f"❌ {tpl_key}", callback_data=f"ad_delete_{brand}_{city}_{tpl_key}"))
        markup.add(types.InlineKeyboardButton("« Назад", callback_data=f"ad_city_{brand}_{city}"))
        bot.send_message(chat_id, "Выберите шаблон для удаления:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('ad_'))
    def handle_ad_callbacks(call: types.CallbackQuery):
        if not is_admin(bot, call.from_user.id, call.message.chat.id):
            return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
        
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        bot.answer_callback_query(call.id)
        parts = call.data.split('_')
        action = parts[1]

        try: bot.delete_message(chat_id, message_id)
        except Exception: pass

        if action == "brand":
            brand = parts[2]
            show_ad_cities_menu(chat_id, brand)
        elif action == "city":
            brand, city = parts[2], parts[3]
            show_ad_actions_menu(chat_id, brand, city)
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
            show_templates_for_deletion(chat_id, brand, city)
        elif action == "delete":
            brand, city, tpl_key = parts[2], parts[3], "_".join(parts[4:])
            if tpl_key in ad_templates.get(brand, {}).get(city, {}):
                del ad_templates[brand][city][tpl_key]
                if save_json_data(AD_TEMPLATES_FILE, ad_templates):
                     bot.send_message(chat_id, f"Шаблон '{tpl_key}' удален.")
                     show_templates_for_deletion(chat_id, brand, city)
                else:
                    bot.send_message(chat_id, "Ошибка сохранения!")
        elif action == 'backtobrand':
            command_ads(call.message)
        elif action == 'backtocity':
            brand = parts[2]
            show_ad_cities_menu(chat_id, brand)

    @bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get("state") == "awaiting_ad_template")
    def receive_ad_template_to_add(message: types.Message):
        user_id = message.from_user.id
        if message.text == '/cancel':
            del user_states[user_id]
            return bot.send_message(message.chat.id, "Добавление шаблона отменено.")
        try:
            name, text = message.text.split('\n', 1)
            name, text = name.strip(), text.strip()
            if not name or not text: raise ValueError
            state_data = user_states[user_id]
            brand, city = state_data['brand'], state_data['city']
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
            if user_id in user_states: del user_states[user_id]
            
    @bot.callback_query_handler(func=lambda call: True)
    def _debug_all_callbacks(call: types.CallbackQuery):
        try:
            bot.answer_callback_query(call.id, f"Необработанный колбэк: {call.data}", show_alert=False)
        except Exception:
            pass
        logging.warning(f"Получен необработанный callback_data -> {call.data} от {get_username(call.from_user)} в чате {call.message.chat.id}")
