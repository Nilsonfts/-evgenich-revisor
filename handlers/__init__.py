# handlers/__init__.py

from . import admin, callbacks, shift, user, voice, wizards

def register_handlers(bot):
    """Регистрирует все обработчики из всех модулей."""
    # Порядок важен: admin первый (для @admin_required команд),
    # затем shift (для /start), user (для общих команд),
    # voice (для голосовых), wizards (для мастеров),
    # callbacks ПОСЛЕДНИЙ (содержит callback обработчики)
    admin.register_admin_handlers(bot)
    shift.register_shift_handlers(bot)
    user.register_user_handlers(bot)
    voice.register_voice_handlers(bot)
    wizards.register_wizard_handlers(bot)
    callbacks.register_callback_handlers(bot)
