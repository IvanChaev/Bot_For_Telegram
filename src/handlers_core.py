# src/handlers_core.py
import asyncio
import json
import logging
import aiohttp
import re
from pathlib import Path
from time import time
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import NetworkError, TimedOut

from .config import (
    OLLAMA_GENERATE, MODEL_NAME, CONTEXT_LENGTH,
    OWNER_ID, BOT_USERNAME, GENERATION_TIMEOUT, BASE_DIR,
    DEFAULT_TEMPERATURE, DEFAULT_NUM_PREDICT
)
from .helpers import (
    is_authorized, should_respond, safe_edit_text,
    safe_delete_message, set_paused_off,
    set_manual_pause, set_auto_pause, set_stopped,
    is_owner, has_admin_rights, is_paused, is_stopped,
    add_pending_message, get_pending_count, pop_pending_message,
    cancel_current_task, current_generation_task, safe_reply,
    clear_pending_messages, is_auto_paused
)
from .chat_history import (
    get_chat_data, set_system_prompt, clear_history,
    add_message_to_history, build_prompt
)
from .voice_utils import (
    generate_voice, transcribe_voice, send_voice_with_retry,
    clear_model_cache
)

logger = logging.getLogger(__name__)

GLOBAL_SETTINGS_FILE = BASE_DIR / "global_settings.json"

def load_global_settings():
    if GLOBAL_SETTINGS_FILE.exists():
        try:
            with open(GLOBAL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"temperature": DEFAULT_TEMPERATURE, "num_predict": DEFAULT_NUM_PREDICT}

def save_global_settings(settings: dict):
    try:
        with open(GLOBAL_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить глобальные настройки: {e}")

async def safe_send_message(update: Update, text: str):
    return await safe_reply(update, text)

_user_last_notify = {}

def can_notify(user_id: int) -> bool:
    now = time()
    if user_id not in _user_last_notify:
        _user_last_notify[user_id] = now
        return True
    if now - _user_last_notify[user_id] >= 20:
        _user_last_notify[user_id] = now
        return True
    return False

async def notify_owner(context: ContextTypes.DEFAULT_TYPE, user_info: str, message: str, chat_title: str):
    if OWNER_ID == 0:
        return
    try:
        text = f"📩 Сообщение от {user_info}\n💬 Чат: {chat_title}\n📝 Текст: {message}"
        await context.bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление владельцу: {e}")

async def generate_with_retry(session, url, payload, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with session.post(url, json=payload, timeout=GENERATION_TIMEOUT) as resp:
                resp.raise_for_status()
                while True:
                    try:
                        line = await asyncio.wait_for(resp.content.readline(), timeout=30.0)
                        if not line:
                            break
                        yield line
                    except asyncio.TimeoutError:
                        logger.warning("Таймаут ожидания чанка от Ollama, но соединение живо")
                        continue
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            logger.warning(f"Сетевая ошибка генерации, попытка {attempt+1}/{max_retries}. Жду {wait} сек...")
            await asyncio.sleep(wait)

async def process_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    global current_generation_task
    if is_stopped():
        logger.debug("process_text_message: бот остановлен, выход")
        return

    chat_id = str(update.effective_chat.id)
    prompt = build_prompt(chat_id, user_text)
    
    chat_data = get_chat_data(chat_id)
    temperature = chat_data.get("temperature")
    num_predict = chat_data.get("num_predict")
    if temperature is None:
        global_settings = load_global_settings()
        temperature = global_settings.get("temperature", DEFAULT_TEMPERATURE)
    if num_predict is None:
        global_settings = load_global_settings()
        num_predict = global_settings.get("num_predict", DEFAULT_NUM_PREDICT)

    # Используем глобальный num_predict без динамического ограничения
    final_num_predict = num_predict
    logger.debug(f"num_predict: {final_num_predict}")

    current_generation_task = asyncio.current_task()
    full_response = ""
    error_sent = False
    error_task = None

    async def send_error_later():
        nonlocal error_sent
        await asyncio.sleep(60)
        if not error_sent:
            error_sent = True
            await safe_reply(update, "❌ Ошибка генерации. Попробуйте позже.")

    try:
        if is_stopped():
            return

        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_ctx": CONTEXT_LENGTH,
                "num_predict": final_num_predict,
                "temperature": temperature,
                "stop": ["<|im_end|>", "<|im_start|>"]
            }
        }

        session = context.bot_data.get("aiohttp_session")
        if session is None:
            logger.warning("aiohttp_session не найдена в bot_data, создаю временную")
            async with aiohttp.ClientSession() as temp_session:
                async for line in generate_with_retry(temp_session, OLLAMA_GENERATE, payload):
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            if "response" in chunk:
                                full_response += chunk["response"]
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        else:
            async for line in generate_with_retry(session, OLLAMA_GENERATE, payload):
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        if "response" in chunk:
                            full_response += chunk["response"]
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

        if is_stopped():
            return

        if not full_response:
            await safe_reply(update, "🤷‍♂️ Модель промолчала.")
            return

        if not re.search(r'[а-яА-Яa-zA-Z0-9]', full_response):
            full_response = "🤔 Не удалось сформулировать ответ. Попробуйте переформулировать вопрос."

        add_message_to_history(chat_id, "user", user_text)
        add_message_to_history(chat_id, "assistant", full_response)

        # Отправляем ответ
        if len(full_response) <= 4096:
            await safe_reply(update, full_response)
        else:
            for i in range(0, len(full_response), 4096):
                if is_stopped():
                    logger.info("Отправка ответа прервана /stop")
                    break
                for retry in range(3):
                    try:
                        await safe_reply(update, full_response[i:i+4096])
                        break
                    except (NetworkError, TimedOut) as e:
                        if retry == 2:
                            raise
                        logger.warning(f"Сетевая ошибка отправки, попытка {retry+1}/3. Жду {2**retry} сек...")
                        await asyncio.sleep(2 ** retry)

        # Если дошли сюда — ответ отправлен, отменяем отложенную ошибку
        if error_task and not error_task.done():
            error_task.cancel()
        error_sent = True

        # Автоматическая пауза 5 секунд
        if not is_stopped():
            set_auto_pause()
            await asyncio.sleep(5)
            if not is_stopped() and is_auto_paused():
                set_paused_off()
                logger.info("Автоматическая пауза снята, проверяем очередь")
                await process_pending_queue()

    except asyncio.CancelledError:
        logger.debug("Генерация отменена")
        if error_task and not error_task.done():
            error_task.cancel()
        raise
    except asyncio.TimeoutError:
        logger.error("Таймаут генерации")
        if error_task is None:
            error_task = asyncio.create_task(send_error_later())
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка соединения с Ollama: {e}")
        if error_task is None:
            error_task = asyncio.create_task(send_error_later())
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}", exc_info=True)
        if error_task is None:
            error_task = asyncio.create_task(send_error_later())
    finally:
        current_generation_task = None

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.voice:
        return
    if not should_respond(update):
        return

    user = update.effective_user
    logger.info(f"Получено голосовое от {user.first_name}")

    status_msg = await safe_send_message(update, "🎤 Распознаю речь...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice_file = await update.message.voice.get_file()
        ogg_bytes = await voice_file.download_as_bytearray()
        text = await transcribe_voice(bytes(ogg_bytes))
        if not text:
            await safe_edit_text(status_msg, "🤷 Не удалось распознать речь.")
            return

        await safe_edit_text(status_msg, f"📝 Распознано: {text}")
        await process_text_message(update, context, text)

    except Exception as e:
        logger.error(f"Ошибка обработки голосового: {e}", exc_info=True)
        await safe_edit_text(status_msg, f"💥 Ошибка распознавания: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    logger.info(f"📩 Получено сообщение от {update.effective_user.id}: {update.message.text}")

    if is_stopped():
        logger.debug("Бот остановлен, сообщение проигнорировано")
        return

    if is_paused():
        if not add_pending_message(update, context):
            await safe_reply(update, "⚠️ Слишком много отложенных сообщений (максимум 5). Подождите, пока бот обработает предыдущие.")
        else:
            logger.debug("Бот на паузе, сообщение добавлено в очередь")
        return

    if not should_respond(update):
        logger.info("❌ should_respond вернул False")
        return

    if not is_owner(update) and can_notify(update.effective_user.id):
        user = update.effective_user
        user_info = f"@{user.username}" if user.username else user.full_name
        chat_title = update.effective_chat.title or "Личное сообщение"
        asyncio.create_task(notify_owner(context, user_info, update.message.text, chat_title))

    user_text = update.message.text.replace(f"@{BOT_USERNAME}", "").strip()
    if not user_text:
        await safe_reply(update, "Ну и чё молчишь? Спрашивай давай.")
        return

    await process_text_message(update, context, user_text)

async def process_pending_queue():
    if is_stopped() or is_paused():
        logger.debug("process_pending_queue: бот на паузе или остановлен, не обрабатываем")
        return
    next_update, next_context = pop_pending_message()
    if next_update is None:
        logger.debug("Очередь пуста")
        return
    logger.info(f"Обрабатываю следующее сообщение из очереди (осталось {get_pending_count()})")
    await handle_message(next_update, next_context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning(f"Сетевая ошибка: {err}. Ждём 5 сек и продолжаем.")
        await asyncio.sleep(5)
    else:
        logger.error(f"Необработанная ошибка: {err}", exc_info=err)