# handlers/__init__.py

from . import admin, callbacks, shift, user, voice, wizards

def register_handlers(bot):
    """Регистрирует все обработчики из всех модулей."""
    admin.register_admin_handlers(bot)
    callbacks.register_callback_handlers(bot)
    shift.register_shift_handlers(bot)
    user.register_user_handlers(bot)
    voice.register_voice_handlers(bot)
    wizards.register_wizard_handlers(bot)
