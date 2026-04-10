# src/handlers_public.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

from .config import OWNER_ID, MODEL_NAME
from .helpers import (
    is_authorized, has_admin_rights, safe_delete_message,
    safe_reply, set_paused_off, set_stopped, is_paused,
    is_stopped, get_help_text
)
from .chat_history import get_chat_data, set_temperature
from .voice_utils import generate_voice, send_voice_with_retry
from .handlers_core import (
    load_global_settings, process_pending_queue, safe_edit_text
)

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_authorized(update):
        await safe_delete_message(update.message)
        return
    if is_stopped():
        if has_admin_rights(update):
            set_paused_off()
            set_stopped(False)
            await process_pending_queue()
            await safe_reply(update, "✅ Бот запущен администратором.\n\n" + get_help_text())
        else:
            await safe_reply(update, "⛔ Бот остановлен администратором. Запустить может только администратор.")
        await safe_delete_message(update.message)
        return
    if is_paused():
        set_paused_off()
        await process_pending_queue()
    await safe_reply(update, get_help_text())
    await safe_delete_message(update.message)

async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_authorized(update):
        await safe_delete_message(update.message)
        return
    await safe_reply(update, get_help_text())
    await safe_delete_message(update.message)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_authorized(update):
        await safe_delete_message(update.message)
        return
    chat_id = str(update.effective_chat.id)
    chat_data = get_chat_data(chat_id)
    global_settings = load_global_settings()
    temp = chat_data.get("temperature")
    if temp is None:
        temp = global_settings.get("temperature", "не установлена")
    num = chat_data.get("num_predict")
    if num is None:
        num = global_settings.get("num_predict", "не установлено")
    prompt = chat_data.get("system_prompt", "не установлен")
    history_len = len(chat_data.get("history", []))
    paused = is_paused()
    stopped = is_stopped()

    text = (
        f"📊 Информация\n"
        f"🆔 Chat ID: {chat_id}\n"
        f"🌡️ Температура (чат): {temp}\n"
        f"📏 Длина ответа (чат): {num} токенов\n"
        f"💬 Системный промпт: {prompt[:100] + '...' if prompt and prompt != 'не установлен' else prompt}\n"
        f"📚 Сообщений в истории: {history_len}\n"
        f"⏸️ Пауза: {'да' if paused else 'нет'}\n"
        f"🛑 Остановлен: {'да' if stopped else 'нет'}\n"
        f"🧠 Модель: {MODEL_NAME}"
    )
    await safe_reply(update, text)
    await safe_delete_message(update.message)

async def tts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg is None:
        return
    if is_stopped() or is_paused():
        await safe_reply(update, "❌ Бот остановлен или на паузе. Используй /start.")
        await safe_delete_message(msg)
        return
    if not is_authorized(update):
        await safe_delete_message(msg)
        return

    status_msg = None
    try:
        text_to_speak = None
        if msg.reply_to_message and msg.reply_to_message.text:
            text_to_speak = msg.reply_to_message.text.strip()
        elif context.args:
            text_to_speak = " ".join(context.args).strip()

        if not text_to_speak:
            await safe_reply(update,
                "ℹ️ Использование:\n"
                "/tts в ответ на сообщение — озвучить это сообщение\n"
                "/tts [текст] — озвучить указанный текст"
            )
            return

        status_msg = await safe_reply(update, "🔊 Генерирую озвучку...")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

        voice_data = await generate_voice(text_to_speak)
        await send_voice_with_retry(context.bot, update.effective_chat.id, voice_data)
        if status_msg:
            await status_msg.delete()
    except Exception as e:
        logger.error(f"Ошибка озвучки: {e}", exc_info=True)
        if status_msg:
            await safe_edit_text(status_msg, "❌ Не удалось озвучить текст.")
    finally:
        await safe_delete_message(msg)

async def temp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    if not is_authorized(update):
        await safe_delete_message(update.message)
        return

    chat_id = str(update.effective_chat.id)
    args = context.args

    if not args:
        chat_data = get_chat_data(chat_id)
        temp = chat_data.get("temperature")
        if temp is None:
            global_settings = load_global_settings()
            temp = global_settings.get("temperature", "не установлена")
        await safe_reply(update, f"🌡️ Текущая температура для этого чата: {temp}")
        await safe_delete_message(update.message)
        return

    try:
        temp = float(args[0].strip())
        if temp < 0.1 or temp > 1.5:
            raise ValueError
        set_temperature(chat_id, temp)
        await safe_reply(update, f"🌡️ Температура для этого чата установлена: {temp}")
        logger.info(f"Temperature for chat {chat_id} set to {temp} by {update.effective_user.id}")
    except:
        await safe_reply(update, "❌ Некорректное значение. Используй число от 0.1 до 1.5")
    await safe_delete_message(update.message)