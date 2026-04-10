import asyncio
import logging
import sys
import aiohttp
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ApplicationBuilder
from telegram.error import TimedOut, NetworkError

from .config import (
    BOT_TOKEN, CONTEXT_LENGTH, MAX_HISTORY_PER_CHAT,
    OWNER_ID, DELETE_COMMANDS, LOG_FILE
)
from .ollama_check import check_ollama_sync
from .handlers_core import (
    voice_handler, handle_message, error_handler
)
from .handlers_public import (
    start_command, commands_command, info_command, tts_command, temp_command
)
from .handlers_admin import (
    pause_command, stop_command, whitelist_command, reply_all_command,
    allow_command, revoke_command, len_command, prompt_command,
    show_prompt_command, clear_command
)
from .handlers_owner import (
    admin_command, readmin_command, list_users_command, list_alias_command,
    blacklist_command, clearlogs_command
)
from .user_manager import add_allowed_user, _get_cache
from .voice_utils import init_whisper
from .chat_history import start_periodic_save, stop_periodic_save

# Логи только в консоль (без файла)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
if sys.platform == "win32":
    logging.getLogger().addHandler(logging.StreamHandler())

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def initialize_app_with_retry(app, max_retries=5):
    for attempt in range(max_retries):
        try:
            await app.initialize()
            logger.info("Приложение инициализировано успешно.")
            return
        except TimedOut:
            if attempt == max_retries - 1:
                logger.critical("Не удалось инициализировать бота из-за сетевых проблем.")
                sys.exit(1)
            wait = 2 ** attempt
            logger.warning(f"Таймаут инициализации, попытка {attempt+1}/{max_retries}. Жду {wait} сек...")
            await asyncio.sleep(wait)
        except Exception as e:
            logger.error(f"Неизвестная ошибка при инициализации: {e}")
            sys.exit(1)


async def main():
    init_whisper()
    if not check_ollama_sync():
        logger.critical("Не удалось подключиться к Ollama. Бот не будет работать.")
        return
    if OWNER_ID != 0:
        add_allowed_user(OWNER_ID)
    # Прогрев кэша пользователей
    _get_cache()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Глобальная aiohttp-сессия для Ollama
    session = aiohttp.ClientSession()
    app.bot_data["aiohttp_session"] = session

    # Регистрация команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("commands", commands_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("tts", tts_command))

    app.add_handler(CommandHandler("temp", temp_command))
    app.add_handler(CommandHandler("len", len_command))

    app.add_handler(CommandHandler("prompt", prompt_command))
    app.add_handler(CommandHandler("p", show_prompt_command))
    app.add_handler(CommandHandler("clear", clear_command))

    app.add_handler(CommandHandler("allow", allow_command))
    app.add_handler(CommandHandler("revoke", revoke_command))
    app.add_handler(CommandHandler("whitelist", whitelist_command))
    app.add_handler(CommandHandler("reply_all", reply_all_command))

    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("readmin", readmin_command))
    app.add_handler(CommandHandler("listusers", list_users_command))
    app.add_handler(CommandHandler("list", list_alias_command))
    app.add_handler(CommandHandler("clearlogs", clearlogs_command))
    app.add_handler(CommandHandler("blacklist", blacklist_command))

    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # Запуск периодического сохранения истории
    start_periodic_save()

    await initialize_app_with_retry(app)
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Сброс старых обновлений
    try:
        await app.bot.get_updates(offset=-1, timeout=1)
        logger.info("Старые обновления сброшены")
    except Exception as e:
        logger.warning(f"Ошибка при сбросе старых обновлений: {e}")

    logger.info(f"Бот запущен. Контекст: {CONTEXT_LENGTH} токенов. История: {MAX_HISTORY_PER_CHAT} пар сообщений. Владелец ID: {OWNER_ID}. Удаление команд: {DELETE_COMMANDS}. Погнали!")

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        stop_periodic_save()
        await session.close()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())