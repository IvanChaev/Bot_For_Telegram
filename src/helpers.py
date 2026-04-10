# src/helpers.py
import asyncio
import logging
from collections import deque
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from .config import BOT_USERNAME, OWNER_ID, DELETE_COMMANDS
from .user_manager import is_user_allowed, is_admin

logger = logging.getLogger(__name__)

# Состояния бота
paused = False
stopped = False
auto_paused = False
pending_messages = deque()
MAX_PENDING = 5

# Текущая задача генерации
current_generation_task: asyncio.Task | None = None

# Для команды reply_all
reply_in_groups = False

def set_reply_in_groups(value: bool):
    global reply_in_groups
    reply_in_groups = value
    logger.info(f"Reply in groups mode set to {value}")

def set_manual_pause():
    global paused, auto_paused, stopped
    paused = True
    auto_paused = False
    stopped = False
    logger.info("Ручная пауза включена")

def set_auto_pause():
    global paused, auto_paused, stopped
    paused = True
    auto_paused = True
    stopped = False
    logger.info("Автоматическая пауза включена")

def set_paused_off():
    global paused, auto_paused
    paused = False
    auto_paused = False
    logger.info("Пауза снята")

def set_stopped(state: bool):
    global stopped, paused, auto_paused
    stopped = state
    if state:
        paused = False
        auto_paused = False
    logger.info(f"Bot stopped = {stopped}, paused = {paused}")

def is_paused():
    return paused

def is_stopped():
    return stopped

def is_auto_paused():
    return auto_paused

def add_pending_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if len(pending_messages) >= MAX_PENDING:
        logger.warning(f"Очередь переполнена ({MAX_PENDING}), сообщение от {update.effective_user.id} отклонено")
        return False
    pending_messages.append((update, context))
    logger.debug(f"Сообщение добавлено в очередь (всего {len(pending_messages)})")
    return True

def pop_pending_message():
    if pending_messages:
        return pending_messages.popleft()
    return None, None

def get_pending_count():
    return len(pending_messages)

def clear_pending_messages():
    pending_messages.clear()
    logger.info("Очередь отложенных сообщений очищена")

def cancel_current_task():
    global current_generation_task
    if current_generation_task and not current_generation_task.done():
        current_generation_task.cancel()
        logger.info("Текущая задача генерации отменена.")

def is_authorized(update: Update) -> bool:
    if OWNER_ID == 0:
        return True
    user = update.effective_user
    if user is None:
        return False
    return is_user_allowed(user.id)

def is_owner(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == OWNER_ID

def has_admin_rights(update: Update) -> bool:
    if OWNER_ID == 0:
        return True
    user = update.effective_user
    if user is None:
        return False
    return user.id == OWNER_ID or is_admin(user.id)

def should_respond(update: Update) -> bool:
    if not is_authorized(update):
        return False

    chat_type = update.message.chat.type
    text = update.message.text or ""

    if chat_type != "private":
        if reply_in_groups:
            logger.info(f"💬 Групповой чат (режим reply_all): {update.effective_chat.title or 'без названия'}")
            return True

    if chat_type == "private":
        logger.info(f"📨 ЛС от {update.effective_user.first_name}: {text}")
        return True

    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == update.message.get_bot().id:
        logger.info(f"↩️ Ответ на сообщение бота в чате {update.effective_chat.title or 'без названия'}")
        return True

    if text:
        if f"@{BOT_USERNAME}" in text:
            logger.info(f"🔔 Упоминание в чате {update.effective_chat.title or 'без названия'}: {text}")
            return True
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == "mention":
                    mention_text = text[entity.offset:entity.offset+entity.length]
                    if mention_text == f"@{BOT_USERNAME}":
                        logger.info(f"🔔 Упоминание (entity) в чате {update.effective_chat.title or 'без названия'}")
                        return True

    logger.debug(f"Сообщение проигнорировано: {text}")
    return False

async def safe_edit_text(message, new_text):
    try:
        await message.edit_text(new_text)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
    except Exception as e:
        logger.debug(f"Сетевая ошибка при редактировании: {e}")

async def safe_delete_message(message):
    if not DELETE_COMMANDS:
        return
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")

async def safe_reply(update: Update, text: str, **kwargs):
    if update.message:
        return await update.message.reply_text(text, **kwargs)
    elif update.effective_chat:
        return await update.effective_chat.send_message(text, **kwargs)
    else:
        logger.error(f"Не удалось отправить ответ: нет контекста. Текст: {text}")
        return None

async def thinking_animation(status_message, stop_event: asyncio.Event):
    dots = ["🧠 Думаю", "🧠 Думаю.", "🧠 Думаю..", "🧠 Думаю..."]
    idx = 0
    while not stop_event.is_set():
        try:
            await safe_edit_text(status_message, dots[idx])
        except Exception as e:
            logger.debug(f"Ошибка анимации (сеть): {e}")
        idx = (idx + 1) % len(dots)
        await asyncio.sleep(2)

async def countdown_and_unpause(update: Update, timer_msg, delay: int = 10):
    for remaining in range(delay, 0, -1):
        await asyncio.sleep(1)
        if not is_paused():
            break
        try:
            await timer_msg.edit_text(f"⏸️ Бот на паузе. Следующий ответ через {remaining} сек...")
        except Exception:
            pass
    if not is_stopped() and is_auto_paused():
        set_paused_off()
    try:
        await timer_msg.delete()
    except Exception:
        pass
    logger.info("Автоматическая пауза снята, проверяем очередь")
    from .handlers_core import process_pending_queue
    asyncio.create_task(process_pending_queue())

def get_help_text() -> str:
    public_commands = (
        "👥 Общедоступные команды:\n"
        "/info — информация о чате и настройках\n"
        "/commands — показать этот список\n"
        "/tts — озвучить текст (в ответ на сообщение или /tts [текст])\n"
        "/temp [0.1-1.5] — установить температуру для этого чата (доступно всем)\n"
    )
    admin_commands = (
        "\n🔧 Администраторы (и владелец):\n"
        "/whitelist on|off — включить/выключить режим белого списка\n"
        "/allow ID — добавить пользователя в белый список\n"
        "/revoke ID — удалить пользователя из белого списка\n"
        "/len число — глобальная длина ответа (токенов)\n"
        "/prompt [текст] — установить системный промпт\n"
        "/p — показать текущий промпт\n"
        "/clear — очистить историю диалога\n"
        "/pause — поставить на паузу (сообщения сохраняются)\n"
        "/stop — полностью остановить (сообщения игнорируются)\n"
        "/start — запустить бота (снять паузу/остановку)\n"
        "/reply_all on|off — отвечать на все сообщения в группах\n"
    )
    owner_commands = (
        "\n👑 Только владелец:\n"
        "/admin ID — назначить админа\n"
        "/readmin ID — снять админа\n"
        "/listusers — список всех пользователей и режимов\n"
        "/blacklist add ID — добавить в чёрный список\n"
        "/blacklist remove ID — удалить из чёрного списка\n"
        "/blacklist — показать чёрный список\n"
        "/clearlogs — очистить файлы логов\n"
    )
    return (
        "Привет! Я бот на базе Ruadapt Qwen3-4B (русскоязычная версия).\n\n"
        f"{public_commands}\n"
        f"{admin_commands}\n"
        f"{owner_commands}\n"
        "Можешь отправлять текст или голосовые сообщения!"
    )