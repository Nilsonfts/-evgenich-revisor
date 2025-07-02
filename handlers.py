# handlers.py
"""
Этот файл содержит все обработчики сообщений и кнопок (хендлеры) для бота.
Он импортирует необходимые функции и переменные из других модулей.
"""
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
    save_history_event, save_json_data,
)
from scheduler import send_end_of_shift_report_for_chat

# Используем openai, если он установлен
try:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None
except ImportError:
    client = None


def register_handlers(bot):
    """Регистрирует все обработчики сообщений и колбэков для бота."""

    # ========================================
    #   ВНУТРЕННИЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
    # ========================================
    def analyze_voice_thread(audio_path: str, user_data: dict, chat_id: int):
        """Анализирует аудио в отдельном потоке, чтобы не блокировать бота."""
        if not client or not ad_templates:
            if os.path.exists(audio_path): os.remove(audio_path)
            return

        chat_config = chat_configs.get(chat_id, {})
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
                    user_data['recognized_ads'].extend(found_templates)
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

    # ========================================
    #   ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ
    # ========================================
    @bot.message_handler(content_types=['voice'])
    def handle_voice_message(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: return

        user_id = message.from_user.id
        username = get_username(message.from_user)
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

        if chat_id not in chat_data: init_shift_data(chat_id)
        if user_id not in chat_data[chat_id]['users']:
            chat_data[chat_id]['users'][user_id] = init_user_data(user_id, username)

        is_new_main = False
        if chat_data[chat_id].get('main_id') is None:
            chat_data[chat_id]['main_id'] = user_id
            chat_data[chat_id]['main_username'] = username
            is_new_main = True

        if chat_data[chat_id]['main_id'] == user_id:
            if is_new_main:
                bot.send_message(chat_id, f"👑 {username} становится главным, записав первое ГС!")
                save_history_event(chat_id, user_id, username, "Стал главным (первое ГС)")

            user_data = chat_data[chat_id]['users'][user_id]

            if not is_new_main and user_data.get('last_voice_time'):
                time_since_last = (now_moscow - user_data['last_voice_time']).total_seconds()
                if time_since_last < VOICE_COOLDOWN_SECONDS:
                    remaining = int(VOICE_COOLDOWN_SECONDS - time_since_last)
                    bot.reply_to(message, f"Слишком часто! Пауза {remaining} сек.", disable_notification=True)
                    return

            if message.voice.duration < VOICE_MIN_DURATION_SECONDS:
                bot.reply_to(message, f"*{random.choice(soviet_phrases.get('too_short', ['Коротко']))}* ({message.voice.duration} сек)")
                return

            bot.send_message(chat_id, f"*{random.choice(soviet_phrases.get('accept', ['Принято']))}*", reply_to_message_id=message.message_id)

            if user_data.get('last_voice_time'):
                delta_minutes = (now_moscow - user_data['last_voice_time']).total_seconds() / 60
                user_data['voice_deltas'].append(delta_minutes)

            user_data['count'] += 1
            user_data['last_voice_time'] = now_moscow
            user_data['voice_durations'].append(message.voice.duration)
            user_data['voice_timeout_reminder_sent'] = False

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
        if chat_id > 0 or chat_data.get(chat_id, {}).get('main_id') != user_id: return
        user_data = chat_data[chat_id]['users'][user_id]
        if user_data.get('on_break'):
            return bot.reply_to(message, "Вы уже на перерыве.")
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        last_break = user_data.get('last_break_time')
        if last_break and (now_moscow - last_break).total_seconds() / 60 < BREAK_DELAY_MINUTES:
            remaining_time = int(BREAK_DELAY_MINUTES - (now_moscow - last_break).total_seconds() / 60)
            return bot.reply_to(message, f"Следующий перерыв можно взять через {remaining_time} мин.")
        user_data.update({
            'on_break': True, 'break_start_time': now_moscow,
            'last_break_time': now_moscow, 'breaks_count': user_data['breaks_count'] + 1,
            'last_break_reminder_time': None
        })
        bot.reply_to(message, f"✅ Перерыв на {BREAK_DURATION_MINUTES} минут начат.")
        save_history_event(chat_id, user_id, get_username(message.from_user), "Ушел на перерыв")

    @bot.message_handler(func=lambda m: m.text and any(word in m.text.lower().split() for word in RETURN_CONFIRM_WORDS))
    def handle_return_message(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        if chat_id > 0 or chat_data.get(chat_id, {}).get('main_id') != user_id: return
        handle_user_return(bot, chat_id, user_id)

    # ========================================
    #   ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
    # ========================================
    @bot.message_handler(commands=['start', 'старт'])
    def handle_start(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: return bot.reply_to(message, "Эта команда работает только в групповом чате.")
        from_user = message.from_user
        username = get_username(from_user)
        if chat_id not in chat_data: init_shift_data(chat_id)
        if from_user.id not in chat_data[chat_id]['users']:
            chat_data[chat_id]['users'][from_user.id] = init_user_data(from_user.id, username)
        if chat_data[chat_id].get('main_id') is not None:
            main_username = chat_data[chat_id].get('main_username', 'Неизвестно')
            return bot.reply_to(message, f"Смена уже занята. Текущий главный: {main_username}.")
        chat_data[chat_id]['main_id'] = from_user.id
        chat_data[chat_id]['main_username'] = username
        bot.send_message(chat_id, f"👑 {username}, вы заступили на смену! Удачи!")
        save_history_event(chat_id, from_user.id, username, "Стал главным на смене (команда /start)")

    @bot.message_handler(commands=['промежуточный', 'check'])
    def handle_check(message: types.Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        data = chat_data.get(chat_id)
        if not data or not data.get('main_id'):
            return bot.reply_to(message, "Смена в этом чате еще не началась.")
        main_user_id = data['main_id']
        if user_id != main_user_id:
            return bot.reply_to(message, f"Эту команду может использовать только текущий главный на смене: {data.get('main_username')}.")
        main_user_data = data.get('users', {}).get(main_user_id)
        shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
        plan_percent = (main_user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
        report_lines = [
            f"📋 *Промежуточный отчет для вас* ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
            f"🗣️ **Голосовых:** {main_user_data['count']} из {shift_goal} ({plan_percent:.0f}%)",
            f"☕ **Перерывов:** {main_user_data['breaks_count']}",
            f"⏳ **Опозданий с перерыва:** {main_user_data['late_returns']}"
        ]
        ad_counts = Counter(main_user_data.get('recognized_ads', []))
        if ad_counts:
            report_lines.append("\n**📝 Анализ контента:**")
            for ad, count in ad_counts.items():
                report_lines.append(f"✔️ {ad} (x{count})")
        bot.reply_to(message, "\n".join(report_lines))

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
            if df.empty or 'ID Ведущего' not in df.columns:
                return bot.send_message(message.chat.id, "В таблице пока нет данных для анализа.")
            df['ID Ведущего'] = pd.to_numeric(df['ID Ведущего'], errors='coerce')
            user_df = df[df['ID Ведущего'] == user_id].copy()
            if user_df.empty:
                return bot.send_message(message.chat.id, f"{username}, не найдено ваших смен в общей статистике.")
            numeric_cols = ['Голосовых (шт)', 'Перерывов (шт)', 'Опозданий (шт)']
            for col in numeric_cols:
                user_df[col] = pd.to_numeric(user_df[col], errors='coerce').fillna(0)
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
            bot.send_message(message.chat.id, report_text)
        except Exception as e:
            logging.error(f"Ошибка анализа Google Sheets для /сводка: {e}")
            bot.send_message(message.chat.id, "Произошла ошибка при анализе данных из таблицы.")

    @bot.message_handler(commands=['help', 'справка'])
    def handle_help(message: types.Message):
        is_user_admin = is_admin(bot, message.from_user.id, message.chat.id)
        help_text_lines = [
            "📖 *Справка по командам бота*", "\n---",
            "**👤 Основные команды для ведущего:**",
            "`/start` или `/старт` — Занять смену, если она свободна.",
            "`/промежуточный` или `/check` — Показать свой личный отчет по текущей смене.",
            "`/сводка` — Посмотреть свою общую статистику за все время.",
            "Для перерыва просто напишите в чат `перерыв`, `обед` или `отдых`.",
            "Для возвращения — `вернулся`, `на месте`.",
        ]
        if is_user_admin:
            help_text_lines.extend([
                "\n---", "**🛠️ Команды для администраторов:**",
                "`/admin` — Открыть интерактивное меню для управления ботом.",
                "Все основные действия выполняются через кнопки в этом меню."
            ])
        bot.reply_to(message, "\n".join(help_text_lines))
    
    # ========================================
    #   ОБРАБОТЧИКИ КОМАНД НАСТРОЙКИ
    # ========================================
    @bot.message_handler(commands=['setup'])
    @admin_required(bot)
    def handle_setup(message):
        chat_id = message.chat.id
        try:
            _, brand, city = message.text.split()
            brand, city = brand.lower(), city.lower()
            if chat_id not in chat_configs: chat_configs[chat_id] = {}
            chat_configs[chat_id].update({'brand': brand, 'city': city})
            save_json_data(CHAT_CONFIG_FILE, chat_configs)
            bot.reply_to(message, f"✅ Чат успешно настроен!\n**Бренд:** `{brand}`\n**Город:** `{city}`")
        except ValueError:
            bot.reply_to(message, "Неверный формат. Используйте: `/setup <бренд> <город>`")

    @bot.message_handler(commands=['set_timezone'])
    @admin_required(bot)
    def set_timezone(message):
        chat_id = message.chat.id
        try:
            offset = message.text.split()[1]
            tz_name = TIMEZONE_MAP.get(offset)
            if not tz_name:
                return bot.reply_to(message, f"❌ Неверный формат смещения. Доступно: {list(TIMEZONE_MAP.keys())}")
            if chat_id not in chat_configs: chat_configs[chat_id] = {}
            chat_configs[chat_id]['timezone'] = tz_name
            save_json_data(CHAT_CONFIG_FILE, chat_configs)
            local_time = datetime.datetime.now(pytz.timezone(tz_name)).strftime('%H:%M:%S')
            bot.send_message(chat_id, f"✅ Часовой пояс установлен на *{tz_name}* (МСК{offset}).\nТекущее время: *{local_time}*.")
        except IndexError:
            bot.reply_to(message, "Пример использования: `/set_timezone +3`")

    @bot.message_handler(commands=['тайминг'])
    @admin_required(bot)
    def set_shift_timing(message):
        chat_id = message.chat.id
        try:
            _, start_time_str, end_time_str = message.text.split()
            datetime.datetime.strptime(start_time_str, '%H:%M')
            datetime.datetime.strptime(end_time_str, '%H:%M')
            if chat_id not in chat_configs: chat_configs[chat_id] = {}
            chat_configs[chat_id].update({'start_time': start_time_str, 'end_time': end_time_str})
            save_json_data(CHAT_CONFIG_FILE, chat_configs)
            bot.send_message(chat_id, f"✅ График смены установлен: с *{start_time_str}* до *{end_time_str}*.")
        except (IndexError, ValueError):
            bot.reply_to(message, "Неверный формат. Пример: `/тайминг 19:00 04:00`")

    @bot.message_handler(commands=['setgoal'])
    @admin_required(bot)
    def set_default_goal(message):
        chat_id = message.chat.id
        try:
            goal = int(message.text.split()[1])
            if goal <= 0: raise ValueError
            if chat_id not in chat_configs: chat_configs[chat_id] = {}
            chat_configs[chat_id]['default_goal'] = goal
            save_json_data(CHAT_CONFIG_FILE, chat_configs)
            bot.send_message(chat_id, f"✅ План по умолчанию для новых смен в этом чате установлен: *{goal}* ГС.")
        except (IndexError, ValueError):
            bot.reply_to(message, "Неверный формат. Укажите положительное число. Пример: `/setgoal 20`")

def get_full_report_text(chat_id: int, user_data: dict, data: dict) -> str:
        """Собирает полный текстовый отчет по текущему статусу смены."""
        shift_goal = data.get('shift_goal', EXPECTED_VOICES_PER_SHIFT)
        plan_percent = (user_data['count'] / shift_goal * 100) if shift_goal > 0 else 0
        avg_delta = sum(user_data.get('voice_deltas', [])) / len(user_data['voice_deltas']) if user_data.get('voice_deltas') else 0
        max_pause = max(user_data.get('voice_deltas', [0]))
        avg_duration = sum(user_data.get('voice_durations', [])) / len(user_data['voice_durations']) if user_data.get('voice_durations') else 0
        
        report_lines = [
            f"📋 **Промежуточный отчет по смене** ({datetime.datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M')})",
            f"🎤 **Ведущий:** {user_data.get('username', 'N/A')}",
            "\n---",
            "**📊 Основная Статистика**",
            f"**Голосовых:** {user_data.get('count', 0)} из {shift_goal} ({plan_percent:.0f}%)",
            f"**Перерывов:** {user_data.get('breaks_count', 0)}",
            f"**Опозданий:** {user_data.get('late_returns', 0)}",
            "\n---",
            "**📈 Аналитика Активности**",
            f"**Средний ритм:** {avg_delta:.1f} мин/ГС" if avg_delta else "**Средний ритм:** Н/Д",
            f"**Макс. пауза:** {max_pause:.1f} мин." if max_pause else "**Макс. пауза:** Н/Д",
            f"**Ср. длина ГС:** {avg_duration:.1f} сек." if avg_duration else "**Ср. длина ГС:** Н/Д"
        ]
        
        ad_counts = Counter(user_data.get('recognized_ads', []))
        if ad_counts:
            report_lines.append("\n---\n**📝 Анализ Контента**")
            for ad, count in ad_counts.items():
                report_lines.append(f"✔️ {ad} (x{count})")
                
        return "\n".join(report_lines)
    
    # ========================================
    #   АДМИНИСТРАТИВНЫЕ ИНСТРУМЕНТЫ И МЕНЮ
    # ========================================
    
    # --- Вложенные функции, чтобы не засорять область видимости ---
    def show_shift_status(chat_id: int):
        data = chat_data.get(chat_id)
        if not data or not data.get('main_id'):
            return bot.send_message(chat_id, "Смена в этом чате еще не началась.")
        user_data = data.get('users', {}).get(data['main_id'])
        if not user_data:
            return bot.send_message(chat_id, "В текущей смене нет данных о ведущем.")
        report_text = get_full_report_text(chat_id, user_data, data)
        bot.send_message(chat_id, report_text)

    def show_overall_rating(chat_id: int):
        if not pd: return bot.send_message(chat_id, "Модуль для анализа данных (pandas) не загружен.")
        bot.send_message(chat_id, "📊 Анализирую общую статистику из Google Таблицы...")
        worksheet = get_sheet()
        if not worksheet: return bot.send_message(chat_id, "Не удалось подключиться к Google Таблице.")
        try:
            df = pd.DataFrame(worksheet.get_all_records())
            if df.empty or 'Тег Ведущего' not in df.columns:
                return bot.send_message(chat_id, "В таблице пока нет данных для анализа.")
            numeric_cols = ['Голосовых (шт)', 'Опозданий (шт)']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
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
            bot.send_message(chat_id, "\n".join(report_lines))
        except Exception as e:
            logging.error(f"Ошибка анализа Google Sheets для /analyze: {e}")
            bot.send_message(chat_id, "Произошла ошибка при анализе данных из таблицы.")

    def find_problem_zones(chat_id: int):
        if not pd: return bot.send_message(chat_id, "Модуль для анализа данных (pandas) не загружен.")
        bot.send_message(chat_id, "🚨 Ищу проблемные зоны в Google Таблице...")
        worksheet = get_sheet()
        if not worksheet: return bot.send_message(chat_id, "Не удалось подключиться к Google Таблице.")
        try:
            df = pd.DataFrame(worksheet.get_all_records())
            if df.empty: return bot.send_message(chat_id, "В таблице нет данных.")
            numeric_cols = ['Выполнение (%)', 'Опозданий (шт)', 'Макс. пауза (мин)']
            for col in numeric_cols:
                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=numeric_cols, inplace=True)
            low_perf = df[df['Выполнение (%)'] < 80]
            latecomers = df[df['Опозданий (шт)'] > 0]
            long_pauses = df[df['Макс. пауза (мин)'] > (VOICE_TIMEOUT_MINUTES * 1.5)]
            report_lines = ["🚨 **Анализ проблемных зон**\n"]
            if not low_perf.empty:
                report_lines.append("*📉 Низкое выполнение плана (<80%):*")
                for _, row in low_perf.iterrows():
                    report_lines.append(f" - {row.get('Тег Ведущего', 'N/A')} ({row.get('Дата', 'N/A')}): *{row['Выполнение (%)']:.0f}%*")
            if not latecomers.empty:
                report_lines.append("\n*⏳ Опоздания с перерывов:*")
                for _, row in latecomers.iterrows():
                    report_lines.append(f" - {row.get('Тег Ведущего', 'N/A')} ({row.get('Дата', 'N/A')}): *{int(row['Опозданий (шт)'])}* раз(а)")
            if not long_pauses.empty:
                report_lines.append("\n*⏱️ Слишком долгие паузы:*")
                for _, row in long_pauses.iterrows():
                    report_lines.append(f" - {row.get('Тег Ведущего', 'N/A')} ({row.get('Дата', 'N/A')}): макс. пауза *{row['Макс. пауза (мин)']:.0f} мин*")
            if len(report_lines) == 1:
                bot.send_message(chat_id, "✅ Проблемных зон по основным критериям не найдено. Отличная работа!")
            else:
                bot.send_message(chat_id, "\n".join(report_lines))
        except Exception as e:
            logging.error(f"Ошибка поиска проблемных зон: {e}")
            bot.send_message(chat_id, f"Произошла ошибка при анализе: {e}")

    def request_broadcast_text(chat_id: int):
        msg = bot.send_message(chat_id, "Введите текст для массовой рассылки всем чатам. Для отмены введите /cancel.")
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
                bot.send_message(int(chat_id_str), f"❗️ **Важное объявление от руководства:**\n\n{text_to_send}")
                sent_count += 1
                time.sleep(0.1)
            except Exception as e:
                logging.error(f"Не удалось отправить рассылку в чат {chat_id_str}: {e}")
        bot.send_message(message.chat.id, f"✅ Рассылка успешно отправлена в {sent_count} из {total_chats} чатов.")

    def restart_shift(chat_id: int, user_id: int):
        if chat_id in chat_data and chat_data[chat_id].get('main_id') is not None:
            init_shift_data(chat_id)
            bot.send_message(chat_id, "🔄 Смена перезапущена. Текущий главный и план сброшены.")
            save_history_event(chat_id, user_id, get_username(bot.get_chat_member(chat_id, user_id).user), "Перезапустил смену")
        else:
            bot.send_message(chat_id, "Активной смены в этом чате и так не было.")

    def force_report(chat_id: int):
        bot.send_message(chat_id, "⏳ Формирую финальный отчет досрочно...")
        send_end_of_shift_report_for_chat(bot, chat_id)

    def export_history(chat_id: int):
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

    def show_setup_menu(chat_id: int):
        config = chat_configs.get(chat_id, {})
        text = (
            f"⚙️ **Настройки чата: {get_chat_title(bot, chat_id)}**\n\n"
            f"*Бренд:* `{config.get('brand', 'Не задан')}`\n"
            f"*Город:* `{config.get('city', 'Не задан')}`\n"
            f"*Часовой пояс:* `{config.get('timezone', 'Не задан (МСК по умолч.)')}`\n"
            f"*График смены:* `{config.get('start_time', 'Н/Д')} - {config.get('end_time', 'Н/Д')}`\n"
            f"*План по ГС:* `{config.get('default_goal', EXPECTED_VOICES_PER_SHIFT)}`\n\n"
            "Отправьте команду для изменения параметра:\n"
            "`/setup <бренд> <город>`\n`/set_timezone +3`\n`/тайминг 19:00 04:00`\n`/setgoal <число>`"
        )
        bot.send_message(chat_id, text, parse_mode="Markdown")

    def show_ad_brands_menu(message: types.Message, is_main_menu: bool):
        markup = types.InlineKeyboardMarkup(row_width=2)
        brands = list(ad_templates.keys())
        for brand in brands:
            markup.add(types.InlineKeyboardButton(brand.upper(), callback_data=f"ad_brand_{brand}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить новый бренд", callback_data="ad_addbrand_form"))
        if is_main_menu:
            markup.add(types.InlineKeyboardButton("« Назад в админ-меню", callback_data="admin_main_menu"))
        try:
            bot.edit_message_text("Выберите бренд для управления рекламой:", message.chat.id, message.message_id, reply_markup=markup)
        except telebot.apihelper.ApiTelegramException:
            pass

    def show_ad_cities_menu(message: types.Message, brand: str):
        markup = types.InlineKeyboardMarkup(row_width=2)
        cities = list(ad_templates.get(brand, {}).keys())
        for city in cities:
            markup.add(types.InlineKeyboardButton(city.capitalize(), callback_data=f"ad_city_{brand}_{city}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить новый город", callback_data=f"ad_addcity_form_{brand}"))
        markup.add(types.InlineKeyboardButton("« Назад к брендам", callback_data="ad_backtobrand"))
        bot.edit_message_text(f"Бренд: *{brand.upper()}*\nВыберите город:", message.chat.id, message.message_id, reply_markup=markup)
    
    def show_ad_actions_menu(message: types.Message, brand: str, city: str):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👁️‍🗨️ Просмотреть шаблоны", callback_data=f"ad_view_{brand}_{city}"),
            types.InlineKeyboardButton("➕ Добавить шаблон", callback_data=f"ad_addform_{brand}_{city}"),
            types.InlineKeyboardButton("➖ Удалить шаблон", callback_data=f"ad_delform_{brand}_{city}"),
            types.InlineKeyboardButton("« Назад к городам", callback_data=f"ad_backtocity_{brand}")
        )
        bot.edit_message_text(f"Бренд: *{brand.upper()}* / Город: *{city.capitalize()}*\nВыберите действие:", message.chat.id, message.message_id, reply_markup=markup)

    def show_templates_for_deletion(call: types.CallbackQuery, brand: str, city: str):
        message = call.message
        templates = ad_templates.get(brand, {}).get(city, {})
        if not templates:
            bot.answer_callback_query(call.id, "Здесь нет шаблонов для удаления.", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for tpl_key in templates.keys():
            markup.add(types.InlineKeyboardButton(f"❌ {tpl_key}", callback_data=f"ad_delete_{brand}_{city}_{tpl_key}"))
        markup.add(types.InlineKeyboardButton("« Назад", callback_data=f"ad_city_{brand}_{city}"))
        bot.edit_message_text("Выберите шаблон для удаления:", message.chat.id, message.message_id, reply_markup=markup)
    
    # --- Основные обработчики команд ---
    @bot.message_handler(commands=['admin'])
    @admin_required(bot)
    def handle_admin_menu(message: types.Message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📊 Статус смены", callback_data="admin_shift_status"),
            types.InlineKeyboardButton("📈 Общий рейтинг", callback_data="admin_analyze_all"),
            types.InlineKeyboardButton("📝 Упр. рекламой", callback_data="admin_manage_ads"),
            types.InlineKeyboardButton("🚨 Проблемные зоны", callback_data="admin_find_problems"),
            types.InlineKeyboardButton("⚙️ Настройка чата", callback_data="admin_chat_setup"),
            types.InlineKeyboardButton("🔄 Перезапуск смены", callback_data="admin_restart_shift"),
            types.InlineKeyboardButton("➡️ Отчет досрочно", callback_data="admin_force_report"),
            types.InlineKeyboardButton("📜 Выгрузить лог", callback_data="admin_export_history")
        )
        if message.from_user.id == BOSS_ID:
            markup.add(types.InlineKeyboardButton("📢 Рассылка (BOSS)", callback_data="admin_broadcast"))
        bot.send_message(message.chat.id, "Добро пожаловать в панель администратора!", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
    def handle_admin_callbacks(call: types.CallbackQuery):
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        message_id = call.message.message_id # Сохраняем ID сообщения
        if not is_admin(bot, user_id, chat_id):
            return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
        bot.answer_callback_query(call.id)
        action = call.data.split('_', 1)[1]
        
        if action == 'shift_status':
            show_shift_status(chat_id)
        elif action == 'analyze_all':
            show_overall_rating(chat_id)
        elif action == 'manage_ads':
            show_ad_brands_menu(call.message, is_main_menu=True)
        elif action == 'find_problems':
            find_problem_zones(chat_id)
        elif action == 'chat_setup':
            show_setup_menu(chat_id)
        elif action == 'restart_shift':
            restart_shift(chat_id, user_id)
        elif action == 'force_report':
            force_report(chat_id)
        elif action == 'export_history':
            export_history(chat_id)
        elif action == 'broadcast':
            if user_id != BOSS_ID:
                return bot.answer_callback_query(call.id, "⛔️ Только для BOSS!", show_alert=True)
            request_broadcast_text(chat_id)
        elif action == 'main_menu': # Обработка кнопки "Назад в меню"
             try:
                 # Просто вызываем функцию, которая отправляет основное меню
                 handle_admin_menu(call.message)
                 # И удаляем старое сообщение с подменю
                 bot.delete_message(chat_id, message_id)
             except Exception as e:
                 logging.warning(f"Не удалось отредактировать/удалить сообщение в admin_main_menu: {e}")


    @bot.callback_query_handler(func=lambda call: call.data.startswith('ad_'))
    def handle_ad_callbacks(call: types.CallbackQuery):
        if not is_admin(bot, call.from_user.id, call.message.chat.id):
            return bot.answer_callback_query(call.id, "⛔️ Доступ запрещен!", show_alert=True)
        bot.answer_callback_query(call.id)
        parts = call.data.split('_')
        action = parts[1]
        if action == "brand":
            brand = parts[2]
            show_ad_cities_menu(call.message, brand)
        elif action == "city":
            brand, city = parts[2], parts[3]
            show_ad_actions_menu(call.message, brand, city)
        elif action == "view":
            brand, city = parts[2], parts[3]
            templates = ad_templates.get(brand, {}).get(city, {})
            if not templates:
                text = "Шаблонов для этого города пока нет."
            else:
                text_lines = [f"📄 **Шаблоны для {brand.upper()} / {city.capitalize()}**\n"]
                for name, content in templates.items():
                    text_lines.append(f"🔹 *{name}*:\n`{content}`\n")
                text = "\n".join(text_lines)
            bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        elif action == "addform":
            brand, city = parts[2], parts[3]
            user_id = call.message.chat.id
            user_states[user_id] = {"state": "awaiting_ad_template", "brand": brand, "city": city}
            bot.send_message(call.message.chat.id, "Отправьте сообщение в формате:\n\n`Название шаблона`\n`Текст шаблона...`\n\nДля отмены введите /cancel")
        elif action == "delform":
            brand, city = parts[2], parts[3]
            show_templates_for_deletion(call, brand, city)
        elif action == "delete":
            brand, city, tpl_key = parts[2], parts[3], "_".join(parts[4:])
            if tpl_key in ad_templates.get(brand, {}).get(city, {}):
                del ad_templates[brand][city][tpl_key]
                if save_json_data(AD_TEMPLATES_FILE, ad_templates):
                    bot.answer_callback_query(call.id, f"Шаблон '{tpl_key}' удален.", show_alert=True)
                    show_templates_for_deletion(call, brand, city)
                else:
                    bot.answer_callback_query(call.id, "Ошибка сохранения!", show_alert=True)
        elif action == 'backtobrand':
            show_ad_brands_menu(call.message, is_main_menu=False)
        elif action == 'backtocity':
            brand = parts[2]
            show_ad_cities_menu(call.message, brand)
        elif action == 'main_menu': # Обработка кнопки "Назад в меню" из подменю рекламы
            handle_admin_menu(call.message)
            bot.delete_message(call.message.chat.id, call.message.message_id)


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
                bot.send_message(message.chat.id, f"✅ Шаблон *'{name}'* успешно добавлен для *{brand.upper()}/{city.capitalize()}*.")
            else:
                bot.send_message(message.chat.id, "❌ Ошибка сохранения файла шаблонов.")
            del user_states[user_id]
        except (ValueError, KeyError):
            bot.send_message(message.chat.id, "Неверный формат. Пожалуйста, отправьте сообщение в формате:\n\n`Название шаблона`\n`Текст шаблона...`")
            if user_id in user_states: del user_states[user_id]
