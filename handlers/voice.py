# handlers/voice.py

import logging
import os
import datetime
import pytz
import random
import threading
from telebot import types

from utils import get_username, init_shift_data, init_user_data, save_history_event
from state import chat_data, ad_templates, chat_configs
from config import VOICE_MIN_DURATION_SECONDS, VOICE_COOLDOWN_SECONDS, OPENAI_API_KEY, BOSS_ID
from phrases import soviet_phrases
from models import UserData

try:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None
except ImportError:
    client = None

def analyze_voice_thread(bot, audio_path: str, user_data: UserData, chat_id: int):
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
            if BOSS_ID: 
                from utils import get_chat_title
                bot.send_message(BOSS_ID, f"❗️ Ошибка анализа речи OpenAI в чате {get_chat_title(bot, chat_id)}:\n`{e}`")
        except Exception as send_e:
            logging.error(f"Не удалось отправить ЛС об ошибке: {send_e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

def register_voice_handlers(bot):

    @bot.message_handler(content_types=['voice'])
    def handle_voice_message(message: types.Message):
        chat_id = message.chat.id
        if chat_id > 0: return # Бот не работает в личных сообщениях

        user_id = message.from_user.id
        username = get_username(message.from_user)
        now_moscow = datetime.datetime.now(pytz.timezone('Europe/Moscow'))

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
                    
                    # Создаем временную папку, если ее нет
                    temp_dir = "temp_voices"
                    os.makedirs(temp_dir, exist_ok=True)
                    file_path = os.path.join(temp_dir, f"voice_{message.message_id}.ogg")
                    
                    with open(file_path, 'wb') as new_file:
                        new_file.write(downloaded_file)
                    
                    threading.Thread(target=analyze_voice_thread, args=(bot, file_path, user_data, chat_id)).start()
                except Exception as e:
                    logging.error(f"Ошибка при скачивании аудиофайла: {e}")
