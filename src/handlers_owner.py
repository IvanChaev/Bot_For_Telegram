# src/handlers_owner.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

from .config import OWNER_ID, LOG_FILE, BASE_DIR
from .helpers import is_owner, safe_delete_message, safe_reply
from .user_manager import (
    add_admin, remove_admin, add_blacklist, remove_blacklist,
    get_blacklist, load_all_data
)

logger = logging.getLogger(__name__)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_owner(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        await safe_reply(update, "ℹ️ Использование: /admin 123456789")
        await safe_delete_message(update.message)
        return
    target = context.args[0].strip()
    if not target.isdigit():
        await safe_reply(update, "ℹ️ Укажи числовой ID пользователя.")
        await safe_delete_message(update.message)
        return
    user_id = int(target)
    if add_admin(user_id):
        await safe_reply(update, f"✅ Пользователь {user_id} назначен админом.")
        logger.info(f"Owner promoted {user_id} to admin")
    else:
        await safe_reply(update, f"ℹ️ Не удалось назначить админа. Пользователь должен быть в списке разрешённых или уже является админом.")
    await safe_delete_message(update.message)

async def readmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_owner(update):
        await safe_delete_message(update.message)
        return
    if not context.args:
        await safe_reply(update, "ℹ️ Использование: /readmin 123456789")
        await safe_delete_message(update.message)
        return
    target = context.args[0].strip()
    if not target.isdigit():
        await safe_reply(update, "ℹ️ Укажи числовой ID пользователя.")
        await safe_delete_message(update.message)
        return
    user_id = int(target)
    if remove_admin(user_id):
        await safe_reply(update, f"✅ Админ {user_id} снят, теперь обычный пользователь.")
        logger.info(f"Owner demoted {user_id} from admin")
    else:
        await safe_reply(update, f"ℹ️ Пользователь {user_id} не является админом.")
    await safe_delete_message(update.message)

async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_owner(update):
        await safe_delete_message(update.message)
        return
    data = load_all_data()
    users = data.get("users", [])
    admins = data.get("admins", [])
    whitelist_enabled = data.get("whitelist_enabled", True)
    blacklist = data.get("blacklist", [])

    lines = []
    lines.append(f"🎛️ Режим белого списка: {'ВКЛЮЧЁН' if whitelist_enabled else 'ВЫКЛЮЧЕН'}")
    lines.append("")
    lines.append("👑 Владелец:")
    try:
        chat = await context.bot.get_chat(OWNER_ID)
        name = f"@{chat.username}" if chat.username else chat.first_name
        lines.append(f"  {OWNER_ID} — {name}")
    except:
        lines.append(f"  {OWNER_ID}")

    lines.append("\n🔧 Администраторы:")
    for uid in admins:
        try:
            chat = await context.bot.get_chat(uid)
            name = f"@{chat.username}" if chat.username else chat.first_name
            lines.append(f"  {uid} — {name}")
        except:
            lines.append(f"  {uid}")

    lines.append("\n👥 Обычные пользователи:")
    for uid in users:
        try:
            chat = await context.bot.get_chat(uid)
            name = f"@{chat.username}" if chat.username else chat.first_name
            lines.append(f"  {uid} — {name}")
        except:
            lines.append(f"  {uid}")

    lines.append("\n🚫 Чёрный список:")
    if blacklist:
        for uid in blacklist:
            try:
                chat = await context.bot.get_chat(uid)
                name = f"@{chat.username}" if chat.username else chat.first_name
                lines.append(f"  {uid} — {name}")
            except:
                lines.append(f"  {uid}")
    else:
        lines.append("  (пусто)")

    await safe_reply(update, "\n".join(lines))
    await safe_delete_message(update.message)

async def list_alias_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_users_command(update, context)

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_owner(update):
        await safe_delete_message(update.message)
        return

    args = context.args
    if not args:
        blacklist = get_blacklist()
        if not blacklist:
            await safe_reply(update, "📭 Чёрный список пуст.")
        else:
            lines = ["🚫 Чёрный список:", ""]
            for uid in blacklist:
                try:
                    chat = await context.bot.get_chat(uid)
                    name = f"@{chat.username}" if chat.username else chat.first_name
                    lines.append(f"  {uid} — {name}")
                except:
                    lines.append(f"  {uid}")
            await safe_reply(update, "\n".join(lines))
        await safe_delete_message(update.message)
        return

    subcommand = args[0].lower()
    if subcommand == "add" and len(args) >= 2:
        try:
            user_id = int(args[1])
            if user_id == OWNER_ID:
                await safe_reply(update, "⛔ Нельзя добавить владельца в чёрный список.")
            elif add_blacklist(user_id):
                await safe_reply(update, f"✅ Пользователь {user_id} добавлен в чёрный список.")
                logger.info(f"Owner blacklisted {user_id}")
            else:
                await safe_reply(update, f"ℹ️ Пользователь {user_id} уже в чёрном списке.")
        except:
            await safe_reply(update, "❌ Некорректный ID.")
    elif subcommand == "remove" and len(args) >= 2:
        try:
            user_id = int(args[1])
            if remove_blacklist(user_id):
                await safe_reply(update, f"✅ Пользователь {user_id} удалён из чёрного списка.")
                logger.info(f"Owner removed {user_id} from blacklist")
            else:
                await safe_reply(update, f"ℹ️ Пользователь {user_id} не в чёрном списке.")
        except:
            await safe_reply(update, "❌ Некорректный ID.")
    else:
        await safe_reply(update, "❌ Использование: /blacklist add <id> | /blacklist remove <id> | /blacklist")
    await safe_delete_message(update.message)

async def clearlogs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_owner(update):
        await safe_delete_message(update.message)
        return
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        warp_log = BASE_DIR / "logs" / "warp_monitor.log"
        if warp_log.exists():
            with open(warp_log, "w", encoding="utf-8") as f:
                f.write("")
        supervisor_log = BASE_DIR / "logs" / "supervisor.log"
        if supervisor_log.exists():
            with open(supervisor_log, "w", encoding="utf-8") as f:
                f.write("")
        await safe_reply(update, "🧹 Логи bot.log, warp_monitor.log и supervisor.log очищены.")
        logger.info("Logs cleared by owner")
    except Exception as e:
        await safe_reply(update, f"❌ Ошибка очистки логов: {e}")
    await safe_delete_message(update.message)