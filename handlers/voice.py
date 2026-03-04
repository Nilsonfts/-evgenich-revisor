# handlers/voice.py

import logging
import os
import datetime
import pytz
import random
import threading
from telebot import types

from utils import get_username, init_shift_data, init_user_data, save_history_event, save_voice_statistics
from state import chat_data, ad_templates, chat_configs, data_lock # ДОБАВЛЕНО: data_lock
from config import VOICE_MIN_DURATION_SECONDS, VOICE_COOLDOWN_SECONDS, OPENAI_API_KEY, BOSS_ID
from phrases import soviet_phrases
from models import UserData
from roles import UserRole, is_weekend_shift, get_default_role_goals, ROLE_EMOJIS, ROLE_DESCRIPTIONS

try:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None
except ImportError:
    client = None

def analyze_voice_thread(bot, audio_path: str, user_data: UserData, chat_id: int):
    """
    Анализирует аудио в отдельном потоке.
    ИЗМЕНЕНО: Добавлена блокировка 'data_lock' для потокобезопасного обновления.
    """
    if not client or not ad_templates:
        if os.path.exists(audio_path): os.remove(audio_path)
        return

    chat_config = chat_configs.get(str(chat_id), {})
    brand, city = chat_config.get("concept") or chat_config.get("brand"), chat_config.get("city")
    if not brand or not city or not (templates_for_location := ad_templates.get(brand, {}).get(city)):
        if os.path.exists(audio_path): os.remove(audio_path)
        return

    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        
        recognized_text = transcript.text.strip()
        if not recognized_text: return

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
                # Потокобезопасно обновляем список
                with data_lock:
                    user_data.recognized_ads.extend(found_templates)
                logging.info(f"GPT ({chat_id}) определил совпадения: {found_templates}")
    except Exception as e:
        logging.error(f"Ошибка OpenAI ({chat_id}): {e}", exc_info=True)
        try:
            if BOSS_ID: 
                from utils import get_chat_title
                bot.send_message(BOSS_ID, f"❗️ Ошибка анализа речи OpenAI в чате {get_chat_title(bot, chat_id)}:\n`{e}`")
        except Exception as send_e:
            logging.error(f"Не удалось отправить ЛС об ошибке: {send_e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

def auto_assign_weekend_roles(shift, user_id, username, chat_id, bot):
    """
    Автоматически назначает роли в выходные дни по порядку голосовых сообщений:
    Первый записавший голосовое = КАРАОКЕ ВЕДУЩИЙ
    Второй записавший голосовое = МС
    """
    if not is_weekend_shift():
        return False
    
    # Считаем количество пользователей с назначенными ролями
    users_with_roles = [u for u in shift.users.values() if hasattr(u, 'role') and u.role]
    
    if len(users_with_roles) >= 2:
        return False  # Уже назначены обе роли
    
    user_data = shift.users[user_id]
    
    # Если роль уже назначена, ничего не делаем
    if hasattr(user_data, 'role') and user_data.role:
        return True
    
    # Назначаем роль по порядку
    if len(users_with_roles) == 0:
        # Первый голосовой = КАРАОКЕ ВЕДУЩИЙ
        assigned_role = UserRole.KARAOKE_HOST.value
        role_order = "первый"
    elif len(users_with_roles) == 1:
        # Второй голосовой = МС
        assigned_role = UserRole.MC.value  
        role_order = "второй"
    else:
        return False
    
    # Назначаем роль и цель
    user_data.role = assigned_role
    day_of_week = datetime.datetime.now().weekday()
    role_goals = get_default_role_goals(day_of_week)
    user_data.goal = role_goals.get(assigned_role, 18)
    
    # Уведомляем о назначении роли
    role_emoji = ROLE_EMOJIS.get(assigned_role, "👤")
    role_desc = ROLE_DESCRIPTIONS.get(assigned_role, assigned_role)
    
    success_text = [
        f"🎉 **ВЫХОДНОЙ ДЕНЬ - АВТОНАЗНАЧЕНИЕ РОЛИ!**",
        f"",
        f"{role_emoji} {username} стал **{role_desc}** ({role_order} голосовое)",
        f"🎯 Цель: {user_data.goal} голосовых сообщений",
        f"",
        f"💡 Следующий записавший голосовое станет {'МС' if assigned_role == UserRole.KARAOKE_HOST.value else 'КАРАОКЕ ВЕДУЩИМ'}!"
    ]
    
    bot.send_message(chat_id, "\n".join(success_text))
    save_history_event(chat_id, user_id, username, f"Автоназначен как {role_desc} в выходной")
    
    return True

def register_voice_handlers(bot):
    @bot.message_handler(content_types=['voice'])
    def handle_voice(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: return  # Игнорируем приватные сообщения
        
        from_user = message.from_user
        user_id = from_user.id
        username = get_username(from_user)
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

        user_data_copy_for_thread = None
        
        # Используем 'with data_lock' для всех операций с общими данными
        with data_lock:
            if chat_id not in chat_data or not chat_data[chat_id]: 
                init_shift_data(chat_id)
            
            shift = chat_data[chat_id]
            if user_id not in shift.users:
                shift.users[user_id] = init_user_data(user_id, username)

            is_new_main = False
            if shift.main_id is None:
                shift.main_id = user_id
                shift.main_username = username
                is_new_main = True

            # Автоматическое назначение ролей в выходные дни
            auto_assign_weekend_roles(shift, user_id, username, chat_id, bot)

            # ИСПРАВЛЕНО: Принимаем голосовые от ВСЕХ участников смены, не только от main_id
            if user_id in shift.users:
                if is_new_main:
                    phrase = random.choice(soviet_phrases.get("system_messages", {}).get('first_voice_new_main', ["👑 {username} становится главным, записав первое ГС!"]))
                    bot.send_message(chat_id, phrase.format(username=username))
                    save_history_event(chat_id, user_id, username, "Стал главным (первое ГС)")

                user_data = shift.users[user_id]
                
                # Проверяем кулдаун голосовых
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

                # Проверяем, на паузе ли пользователь
                if user_data.on_pause:
                    pause_start = datetime.datetime.fromisoformat(user_data.pause_start_time)
                    elapsed = (now_moscow - pause_start).total_seconds() / 60
                    remaining = max(0, 40 - elapsed)
                    if remaining > 0:
                        user_data.on_pause = False
                        user_data.pause_end_time = now_moscow.isoformat()
                        bot.send_message(chat_id, 
                            f"⏯️ **ПАУЗА ЗАВЕРШЕНА** голосовым сообщением!\n"
                            f"✅ Все счетчики возобновлены. Голосовое засчитано!")
                    else:
                        user_data.on_pause = False
                        user_data.pause_end_time = now_moscow.isoformat()

                # Если на перерыве — возвращение
                if user_data.on_break:
                    from utils import handle_user_return
                    handle_user_return(bot, chat_id, user_id)

                bot.send_message(chat_id, f"*{random.choice(soviet_phrases.get('accept', ['Принято']))}*", reply_to_message_id=message.message_id)

                if user_data.last_voice_time:
                    delta_minutes = (now_moscow - datetime.datetime.fromisoformat(user_data.last_voice_time)).total_seconds() / 60
                    user_data.voice_deltas.append(delta_minutes)

                user_data.count += 1
                user_data.last_voice_time = now_moscow.isoformat()
                user_data.voice_durations.append(message.voice.duration)
                user_data.last_activity_reminder_time = None

                # Копируем объект user_data, чтобы передать его в поток
                user_data_copy_for_thread = user_data

                voice_duration = message.voice.duration
                
                # Сохраняем статистику голосового в базу данных
                save_voice_statistics(chat_id, user_id, username, voice_duration)

        # Запускаем анализ голоса вне блокировки
        if client and user_data_copy_for_thread is not None:
            try:
                file_info = bot.get_file(message.voice.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                temp_dir = "temp_voices"
                os.makedirs(temp_dir, exist_ok=True)
                file_path = os.path.join(temp_dir, f"voice_{message.message_id}.ogg")
                
                with open(file_path, 'wb') as new_file:
                    new_file.write(downloaded_file)
                
                # Передаем копию данных в поток
                threading.Thread(target=analyze_voice_thread, args=(bot, file_path, user_data_copy_for_thread, chat_id)).start()
            except Exception as e:
                logging.error(f"Ошибка при скачивании аудиофайла: {e}")
