# help_system.py
"""
Система помощи для бота с поддержкой ролей
"""

from telebot import types
from roles import UserRole, ROLE_EMOJIS, ROLE_DESCRIPTIONS, get_current_day_type, get_roles_for_day_type
from utils import is_admin, get_username
from config import BOSS_ID

def get_user_help_text() -> str:
    """Возвращает текст помощи для обычных пользователей"""
    current_day_type = get_current_day_type()
    available_roles = get_roles_for_day_type(current_day_type)
    
    help_lines = [
        "📘 **СПРАВКА ДЛЯ ПОЛЬЗОВАТЕЛЕЙ** 📘",
        "",
        f"📅 **Сегодня: {current_day_type.value} день**",
        f"🎭 **Доступные роли:**"
    ]
    
    for role in available_roles:
        emoji = ROLE_EMOJIS.get(role, "👤")
        description = ROLE_DESCRIPTIONS.get(role, role)
        help_lines.append(f"   {emoji} {description}")
    
    help_lines.extend([
        "",
        "🎯 **ОСНОВНЫЕ КОМАНДЫ:**",
        "",
        "`/start` или `/старт`",
        "🎬 Занять смену (автоматически назначает роль по расписанию)",
        "",
        "`/start караоке` или `/start МС`", 
        "🎭 Занять смену с конкретной ролью (если доступно)",
        "",
        "`/промежуточный` или `/check`",
        "📊 Показать личный отчет по текущей смене",
        "",
        "`/сводка`",
        "📈 Общая статистика за все время работы",
        "",
        "`/передать`",
        "🔄 Передать смену другому (ответьте на его сообщение)",
        "",
        "☕️ **ПЕРЕРЫВЫ:**",
        "Просто напишите: `перерыв`, `обед`, `отдых`, `покурить`",
        "",
        "✅ **ВОЗВРАЩЕНИЕ:**",
        "Напишите: `вернулся`, `на месте`, `готов`",
        "",
        "🎤 **ГОЛОСОВЫЕ СООБЩЕНИЯ:**",
        "Отправляйте голосовые для подсчета активности",
        "",
        "❓ **ДОПОЛНИТЕЛЬНАЯ ПОМОЩЬ:**",
        "`/help` - показать эту справку",
        "`/роли` - информация о ролях и расписании"
    ])
    
    return "\n".join(help_lines)

def get_admin_help_text(user_id: int) -> str:
    """Возвращает текст помощи для администраторов"""
    help_lines = [
        "🛠️ **СПРАВКА ДЛЯ АДМИНИСТРАТОРОВ** 🛠️",
        "",
        "⚜️ **ПАНЕЛЬ УПРАВЛЕНИЯ:**",
        "`/admin` - открыть интерактивную админ-панель",
        "",
        "📊 **МОНИТОРИНГ И ОТЧЕТЫ:**",
        "`/status` - статус текущих смен",
        "`/rating` - рейтинг всех сотрудников", 
        "`/problems` - поиск проблемных зон",
        "`/log` - выгрузить лог смены",
        "",
        "🎭 **УПРАВЛЕНИЕ РОЛЯМИ:**",
        "`/роли` - настройка ролей и расписания",
        "`/статистика_ролей` - статистика по ролям",
        "",
        "⚙️ **УПРАВЛЕНИЕ СМЕНАМИ:**",
        "`/restart` - принудительный перезапуск смены",
        "`/report` - досрочное завершение смены",
        "`/time [минуты]` - настройка тайм-аута активности",
        "",
        "🤖 **УПРАВЛЕНИЕ БОТОМ:**",
        "`/bot_status` - статус работы бота",
        "`/bot_off` или `/выключить` - выключить бота",
        "`/bot_on` или `/включить` - включить бота",
        "",
        "🔧 **НАСТРОЙКИ:**",
        "`/setup_wizard` - мастер настройки чата",
        "`/ads` - управление рекламными шаблонами",
    ]
    
    if user_id == BOSS_ID:
        help_lines.extend([
            "",
            "👑 **ФУНКЦИИ BOSS:**",
            "`/broadcast` - рассылка во все чаты",
            "`/global_stats` - глобальная статистика",
        ])
    
    help_lines.extend([
        "",
        "💡 **ПОДСКАЗКА:**",
        "Используйте `/admin` для удобного управления через кнопки!",
        "",
        "📱 **БЫСТРЫЕ КОМАНДЫ:**",
        "`/helpadmin` - показать эту справку",
        "`/help` - справка для пользователей"
    ])
    
    return "\n".join(help_lines)

def get_roles_info_text() -> str:
    """Возвращает информацию о ролях и расписании"""
    current_day_type = get_current_day_type()
    current_roles = get_roles_for_day_type(current_day_type)
    
    info_lines = [
        "🎭 **ИНФОРМАЦИЯ О РОЛЯХ** 🎭",
        "",
        "📅 **РАСПИСАНИЕ РАБОТЫ:**",
        "",
        "🗓️ **Будние дни (вс-чт):**",
        f"   {ROLE_EMOJIS[UserRole.KARAOKE_HOST.value]} {ROLE_DESCRIPTIONS[UserRole.KARAOKE_HOST.value]} - 1 человек",
        "   📊 Цель: 15 голосовых сообщений",
        "",
        "🎉 **Выходные дни (пт-сб):**",
        f"   {ROLE_EMOJIS[UserRole.KARAOKE_HOST.value]} {ROLE_DESCRIPTIONS[UserRole.KARAOKE_HOST.value]} - 1 человек",
        f"   {ROLE_EMOJIS[UserRole.MC.value]} {ROLE_DESCRIPTIONS[UserRole.MC.value]} - 1 человек",
        "   📊 Цели: Караоке - 15, МС - 10 голосовых",
        "",
        f"🕐 **СЕГОДНЯ ({current_day_type.value} день):**",
    ]
    
    for role in current_roles:
        emoji = ROLE_EMOJIS.get(role, "👤")
        description = ROLE_DESCRIPTIONS.get(role, role)
        info_lines.append(f"   ✅ {emoji} {description}")
    
    info_lines.extend([
        "",
        "🎯 **ОПИСАНИЕ РОЛЕЙ:**",
        "",
        f"{ROLE_EMOJIS[UserRole.KARAOKE_HOST.value]} **Караоке ведущий:**",
        "• Ведет караоке программу",
        "• Взаимодействует с гостями",
        "• Объявляет песни и поддерживает атмосферу",
        "• Рассказывает рекламные блоки",
        "",
        f"{ROLE_EMOJIS[UserRole.MC.value]} **Ведущий-аниматор (МС):**",
        "• Проводит конкурсы и игры",
        "• Развлекает публику между песнями",
        "• Помогает караоке ведущему",
        "• Дополнительная анимация зала",
        "",
        "📋 **КАК ЗАНЯТЬ РОЛЬ:**",
        "`/start` - автоматическое назначение роли",
        "`/start караоке` - занять роль караоке ведущего",
        "`/start МС` - занять роль МС (если доступно)",
    ])
    
    return "\n".join(info_lines)

def register_help_handlers(bot):
    """Регистрирует обработчики команд помощи"""
    
    @bot.message_handler(commands=['help', 'помощь'])
    def handle_help(message: types.Message):
        """Обработчик команды /help"""
        help_text = get_user_help_text()
        bot.reply_to(message, help_text, parse_mode="Markdown")
    
    @bot.message_handler(commands=['helpadmin', 'админпомощь'])
    def handle_admin_help(message: types.Message):
        """Обработчик команды /helpadmin"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        if not is_admin(bot, user_id, chat_id):
            bot.reply_to(message, "❌ Эта команда доступна только администраторам.")
            return
        
        help_text = get_admin_help_text(user_id)
        bot.reply_to(message, help_text, parse_mode="Markdown")
    
    @bot.message_handler(commands=['роли', 'roles'])
    def handle_roles_info(message: types.Message):
        """Обработчик команды /роли"""
        info_text = get_roles_info_text()
        bot.reply_to(message, info_text, parse_mode="Markdown")
