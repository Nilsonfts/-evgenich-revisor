# handlers/admin.py

import logging
import os
import datetime
import pandas as pd
import random
import time
import pytz
from telebot import types

from utils import admin_required, save_json_data, generate_detailed_report, get_username, get_chat_title
from state import chat_data, user_history, chat_configs, user_states
from config import CHAT_CONFIG_FILE, VOICE_TIMEOUT_MINUTES, BOSS_ID, TIMEZONE_MAP
from g_sheets import get_sheet
from scheduler import send_end_of_shift_report_for_chat
from phrases import soviet_phrases
from database import db  # Импортируем базу данных

def register_admin_handlers(bot):
    @bot.message_handler(commands=['bot_off', 'выключить'])
    @admin_required(bot)
    def handle_bot_disable(message: types.Message):
        """Выключает бота для текущего чата."""
        chat_id = message.chat.id
        admin_id = message.from_user.id
        admin_username = get_username(message.from_user)
        
        # Выключаем бота в базе данных
        db.set_bot_enabled(chat_id, False, admin_id)
        
        # Сохраняем событие
        db.save_event(chat_id, admin_id, admin_username, "bot_disabled", "Бот выключен администратором")
        
        bot.send_message(chat_id, 
            f"🔴 **Бот выключен администратором {admin_username}**\n\n"
            "Для включения используйте команду `/bot_on` или `/включить`",
            parse_mode="Markdown")
        
        logging.info(f"Бот выключен в чате {chat_id} администратором {admin_username} (ID: {admin_id})")

    @bot.message_handler(commands=['bot_on', 'включить'])
    @admin_required(bot)
    def handle_bot_enable(message: types.Message):
        """Включает бота для текущего чата."""
        chat_id = message.chat.id
        admin_id = message.from_user.id
        admin_username = get_username(message.from_user)
        
        # Включаем бота в базе данных
        db.set_bot_enabled(chat_id, True, admin_id)
        
        # Сохраняем событие
        db.save_event(chat_id, admin_id, admin_username, "bot_enabled", "Бот включен администратором")
        
        bot.send_message(chat_id, 
            f"🟢 **Бот включен администратором {admin_username}**\n\n"
            "Бот снова обрабатывает команды и сообщения.",
            parse_mode="Markdown")
        
        logging.info(f"Бот включен в чате {chat_id} администратором {admin_username} (ID: {admin_id})")

    @bot.message_handler(commands=['bot_status'])
    @admin_required(bot)
    def handle_bot_status_check(message: types.Message):
        """Показывает статус работы бота."""
        chat_id = message.chat.id
        is_enabled = db.is_bot_enabled(chat_id)
        
        status_icon = "🟢" if is_enabled else "🔴"
        status_text = "включен" if is_enabled else "выключен"
        
        bot.reply_to(message, 
            f"{status_icon} **Статус бота:** {status_text}\n\n"
            f"Команды управления:\n"
            f"• `/bot_off` или `/выключить` — выключить бота\n"
            f"• `/bot_on` или `/включить` — включить бота\n"
            f"• `/bot_status` — проверить статус",
            parse_mode="Markdown")

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
            "",
            "**🤖 УПРАВЛЕНИЕ БОТОМ:**",
            "`/bot_status` — Статус работы бота",
            "`/bot_off` или `/выключить` — Выключить бота",
            "`/bot_on` или `/включить` — Включить бота",
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
                rank_icon = medals.get(i, f"{i+1}.")
                username = row['Тег Ведущего']
                avg_voices = row['avg_voices']
                lateness_percent = row['lateness_percent']
                total_shifts = row['total_shifts']
                
                report_lines.append(f"{rank_icon} {username} — Ср. ГС: {avg_voices:.1f} | Опоздания: {lateness_percent:.0f}% | Смен: {total_shifts}")
            bot.send_message(chat_id, "\n".join(report_lines))
        except Exception as e:
            logging.error(f"Ошибка анализа Google Sheets для /rating: {e}")
            bot.send_message(chat_id, "Произошла ошибка при выполнении команды.")
        
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
                report_lines.append("*📉 Низкое выполнение плана (меньше 80%):*")
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
    
    @bot.message_handler(commands=['report'])
    @admin_required(bot)
    def command_report(message: types.Message):
        """Досрочный отчет по команде администратора."""
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
        if not text_to_send: 
            msg = bot.reply_to(message, "Текст рассылки не может быть пустым. Попробуйте снова или введите /cancel.")
            bot.register_next_step_handler(msg, process_broadcast_text)
            return

        sent_count = 0
        failed_count = 0
        total_chats = len(list(chat_configs.keys()))
        
        if total_chats == 0:
            return bot.send_message(message.chat.id, "Нет настроенных чатов для рассылки.")

        bot.send_message(message.chat.id, f"Начинаю рассылку в {total_chats} чатов...")
        
        for chat_id_str in chat_configs.keys():
            try:
                bot.send_message(int(chat_id_str), f"❗️ **Важное объявление от руководства:**\n\n{text_to_send}", parse_mode="Markdown")
                sent_count += 1
                time.sleep(0.1) # Небольшая задержка, чтобы не превышать лимиты Telegram
            except Exception as e:
                failed_count += 1
                logging.error(f"Не удалось отправить рассылку в чат {chat_id_str}: {e}")
        
        bot.send_message(message.chat.id, f"✅ Рассылка завершена.\nУспешно отправлено: {sent_count}\nНе удалось отправить: {failed_count}")

    @bot.message_handler(commands=['debug_config'])
    @admin_required(bot)
    def command_debug_config(message: types.Message):
        """Показывает текущую конфигурацию чата для диагностики."""
        chat_id = message.chat.id
        chat_id_str = str(chat_id)
        
        # Получаем конфигурацию чата
        config = chat_configs.get(chat_id_str, {})
        
        # Получаем данные о текущей смене
        shift_data = chat_data.get(chat_id)
        
        # Получаем текущее время в разных часовых поясах
        moscow_time = datetime.datetime.now(pytz.timezone('Europe/Moscow'))
        
        tz_name = config.get('timezone', 'Europe/Moscow')
        try:
            local_tz = pytz.timezone(tz_name)
            local_time = datetime.datetime.now(local_tz)
        except Exception as e:
            local_time = f"Ошибка: {e}"
        
        debug_text = [
            "🔍 **Диагностика конфигурации чата**\n",
            f"**ID чата:** `{chat_id}`",
            f"**Московское время:** `{moscow_time.strftime('%H:%M:%S %d.%m.%Y')}`",
            f"**Локальное время:** `{local_time.strftime('%H:%M:%S %d.%m.%Y') if hasattr(local_time, 'strftime') else local_time}`",
            "",
            "**Конфигурация:**",
            f"  • Часовой пояс: `{tz_name}`",
            f"  • Время окончания: `{config.get('end_time', '04:00 (по умолчанию)')}`",
            f"  • Концепция: `{config.get('concept', 'Не задана')}`",
            f"  • Тайм-аут ГС: `{config.get('voice_timeout', VOICE_TIMEOUT_MINUTES)} мин`",
            "",
            "**Текущая смена:**"
        ]
        
        if shift_data and shift_data.main_id:
            main_user = shift_data.users.get(shift_data.main_id)
            username = main_user.username if main_user else "Неизвестно"
            debug_text.extend([
                f"  • Статус: `Активна`",
                f"  • Ведущий: `{username}`",
                f"  • ГС: `{main_user.count if main_user else 0}/{shift_data.shift_goal}`",
                f"  • Начало смены: `{shift_data.shift_start_time}`",
                f"  • Последний отчет: `{getattr(shift_data, 'last_report_date', 'Не отправлялся')}`"
            ])
        else:
            debug_text.append("  • Статус: `Не активна`")
        
        bot.send_message(chat_id, "\n".join(debug_text), parse_mode="Markdown")

    @bot.message_handler(commands=['marketing_analytics', 'маркетинг'])
    @admin_required(bot)
    def handle_marketing_analytics(message: types.Message):
        """Показывает маркетинговую аналитику за период."""
        chat_id = message.chat.id
        
        # Получаем статистику из базы данных
        analytics = db.get_marketing_analytics(chat_id, days=7)  # За последние 7 дней
        
        if not analytics:
            bot.send_message(chat_id, 
                "📊 **Маркетинговая Аналитика**\n\n"
                "❌ Недостаточно данных за последние 7 дней.\n"
                "Начните смены для получения статистики.",
                parse_mode="Markdown")
            return
        
        # Формируем отчет
        text = "📊 **Маркетинговая Аналитика** (7 дней)\n\n"
        
        text += f"**📈 Общая Эффективность:**\n"
        text += f"• Смен проведено: {analytics.get('total_shifts', 0)}\n"
        text += f"• Среднее выполнение плана: {analytics.get('avg_plan_completion', 0):.1f}%\n"
        text += f"• Общее время активности: {analytics.get('total_active_time', 0):.1f} часов\n\n"
        
        text += f"**🎯 Показатели Качества:**\n"
        text += f"• Средний ритм работы: {analytics.get('avg_rhythm', 0):.1f} мин/ГС\n"
        text += f"• Среднее время перерыва: {analytics.get('avg_break_time', 0):.1f} мин\n"
        text += f"• Опозданий с перерыва: {analytics.get('total_late_returns', 0)}\n\n"
        
        text += f"**📝 Контент-Аналитика:**\n"
        top_ads = analytics.get('top_ads', [])
        if top_ads:
            for i, (ad, count) in enumerate(top_ads[:5], 1):
                text += f"  {i}. {ad}: {count} раз\n"
        else:
            text += "  Нет данных по контенту\n"
        
        text += f"\n**💡 Ключевые Инсайты:**\n"
        
        avg_completion = analytics.get('avg_plan_completion', 0)
        if avg_completion >= 90:
            text += "✅ Отличные результаты! Команда стабильно выполняет план.\n"
        elif avg_completion >= 70:
            text += "👍 Хорошие результаты, есть потенциал для роста.\n"
        else:
            text += "⚠️ Показатели ниже ожидаемых, требуется анализ причин.\n"
        
        avg_rhythm = analytics.get('avg_rhythm', 0)
        if avg_rhythm <= 3:
            text += "⚡ Высокий темп работы поддерживает активность гостей.\n"
        elif avg_rhythm >= 6:
            text += "🐌 Стоит работать над увеличением темпа активности.\n"
        
        # Добавляем кнопки для дополнительных действий
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📊 Детальный отчет", callback_data="marketing_detailed"),
            types.InlineKeyboardButton("📈 Тренды", callback_data="marketing_trends")
        )
        markup.add(
            types.InlineKeyboardButton("💡 Рекомендации", callback_data="marketing_recommendations")
        )
        
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
