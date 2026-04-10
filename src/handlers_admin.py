# src/handlers_admin.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

from .config import OWNER_ID
from .helpers import (
    is_owner, has_admin_rights, safe_delete_message, safe_reply,
    set_reply_in_groups, reply_in_groups, cancel_current_task,
    set_manual_pause, set_stopped, clear_pending_messages
)
from .chat_history import set_system_prompt, clear_history, get_chat_data
from .voice_utils import clear_model_cache
from .handlers_core import load_global_settings, save_global_settings
from .user_manager import (
    add_allowed_user, remove_allowed_user, set_whitelist_enabled,
    is_whitelist_enabled, load_admins
)

logger = logging.getLogger(__name__)

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    cancel_current_task()
    set_manual_pause()
    await safe_reply(update, "⏸️ Бот на паузе. Для возобновления /start.")
    logger.info(f"Pause activated by {update.effective_user.id}")
    await safe_delete_message(update.message)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    cancel_current_task()
    clear_pending_messages()
    set_stopped(True)
    await safe_reply(update, "🛑 Бот полностью остановлен. Используй /start для возобновления работы.")
    logger.info(f"Stop activated by {update.effective_user.id}")
    await safe_delete_message(update.message)

async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        current = "включён" if is_whitelist_enabled() else "выключен"
        await safe_reply(update, f"ℹ️ Режим белого списка: {current}. Использование: /whitelist on|off")
        await safe_delete_message(update.message)
        return
    arg = context.args[0].lower()
    if arg == "on":
        set_whitelist_enabled(True)
        await safe_reply(update, "✅ Белый список включён. Бот отвечает только разрешённым пользователям.")
    elif arg == "off":
        set_whitelist_enabled(False)
        await safe_reply(update, "✅ Белый список выключен. Бот отвечает всем (кроме чёрного списка).")
    else:
        await safe_reply(update, "❌ Используй /whitelist on или /whitelist off")
    await safe_delete_message(update.message)

async def reply_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        current = "включён" if reply_in_groups else "выключен"
        await safe_reply(update, f"ℹ️ Режим ответа на все сообщения в группах: {current}. Использование: /reply_all on|off")
        await safe_delete_message(update.message)
        return
    arg = context.args[0].lower()
    if arg == "on":
        set_reply_in_groups(True)
        await safe_reply(update, "✅ Режим ответа на все сообщения в группах включён. Бот будет отвечать на любое сообщение.")
    elif arg == "off":
        set_reply_in_groups(False)
        await safe_reply(update, "✅ Режим ответа на все сообщения в группах выключен. Бот отвечает только на упоминания и ответы.")
    else:
        await safe_reply(update, "❌ Используй /reply_all on или /reply_all off")
    await safe_delete_message(update.message)

async def allow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        await safe_reply(update, "ℹ️ Использование: /allow 123456789")
        await safe_delete_message(update.message)
        return
    target = context.args[0].strip()
    if not target.isdigit():
        await safe_reply(update, "ℹ️ Укажи числовой ID пользователя.")
        await safe_delete_message(update.message)
        return
    user_id = int(target)
    if user_id == OWNER_ID:
        await safe_reply(update, "⛔ Нельзя добавить владельца через /allow.")
        await safe_delete_message(update.message)
        return
    if user_id in load_admins():
        await safe_reply(update, "ℹ️ Этот пользователь уже администратор. Используй /readmin для понижения.")
        await safe_delete_message(update.message)
        return
    if add_allowed_user(user_id):
        await safe_reply(update, f"✅ Пользователь {user_id} добавлен в список разрешённых.")
        logger.info(f"User {user_id} added by {update.effective_user.id}")
    else:
        await safe_reply(update, f"ℹ️ Пользователь {user_id} уже в списке.")
    await safe_delete_message(update.message)

async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        await safe_reply(update, "ℹ️ Использование: /revoke 123456789")
        await safe_delete_message(update.message)
        return
    target = context.args[0].strip()
    if not target.isdigit():
        await safe_reply(update, "ℹ️ Укажи числовой ID пользователя.")
        await safe_delete_message(update.message)
        return
    user_id = int(target)
    if user_id == OWNER_ID:
        await safe_reply(update, "⛔ Нельзя удалить владельца.")
        await safe_delete_message(update.message)
        return
    if user_id in load_admins() and not is_owner(update):
        await safe_reply(update, "⛔ Администраторы не могут удалять других администраторов.")
        await safe_delete_message(update.message)
        return
    if remove_allowed_user(user_id):
        await safe_reply(update, f"✅ Пользователь {user_id} удалён из списка разрешённых.")
        logger.info(f"User {user_id} removed by {update.effective_user.id}")
    else:
        await safe_reply(update, f"ℹ️ Пользователь {user_id} не найден в списке обычных пользователей.")
    await safe_delete_message(update.message)

async def len_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        await safe_reply(update, "ℹ️ Использование: /len 512 (или 1024)")
        await safe_delete_message(update.message)
        return
    try:
        num = int(context.args[0].strip())
        if num <= 0:
            raise ValueError
        settings = load_global_settings()
        settings["num_predict"] = num
        save_global_settings(settings)
        await safe_reply(update, f"📏 Глобальная длина ответа: {num} токенов")
        logger.info(f"Global num_predict set to {num} by {update.effective_user.id}")
    except:
        await safe_reply(update, "❌ Некорректное значение. Используй целое число > 0")
    await safe_delete_message(update.message)

async def prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    chat_id = str(update.effective_chat.id)
    args = update.message.text.split(maxsplit=1)
    if len(args) == 1:
        set_system_prompt(chat_id, None)
        await safe_reply(update, "🔓 Системный промпт удалён.")
    else:
        prompt_text = args[1].strip()
        set_system_prompt(chat_id, prompt_text)
        await safe_reply(update, f"🔒 Системный промпт установлен:\n{prompt_text}")
    await safe_delete_message(update.message)

async def show_prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    chat_id = str(update.effective_chat.id)
    chat_data = get_chat_data(chat_id)
    system_prompt = chat_data.get("system_prompt")
    if system_prompt:
        await safe_reply(update, f"Текущий системный промпт:\n\n{system_prompt}")
    else:
        await safe_reply(update, "ℹ️ Системный промпт не установлен.")
    await safe_delete_message(update.message)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not has_admin_rights(update):
        await safe_delete_message(update.message)
        return
    chat_id = str(update.effective_chat.id)
    clear_history(chat_id)
    await clear_model_cache()
    await safe_reply(update, "🧹 История диалога очищена. Модель полностью забыла предыдущий разговор.")
    await safe_delete_message(update.message)