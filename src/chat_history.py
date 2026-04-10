import json
import asyncio
import logging
from datetime import datetime
from .config import HISTORY_FILE, MAX_HISTORY_PER_CHAT, DEFAULT_TEMPERATURE, DEFAULT_NUM_PREDICT

logger = logging.getLogger(__name__)

# --- Очередь накопления сообщений для периодической записи ---
_pending_updates = {}   # chat_id -> list of new messages
_save_task = None
_SAVE_INTERVAL = 10     # секунд

def _merge_and_save():
    """Синхронное сохранение всех накопленных данных в файл (вызывается в потоке)."""
    if not _pending_updates:
        return
    data = load_chat_data()
    for chat_id, new_messages in _pending_updates.items():
        if chat_id not in data:
            data[chat_id] = {
                "system_prompt": None,
                "history": [],
                "temperature": DEFAULT_TEMPERATURE,
                "num_predict": DEFAULT_NUM_PREDICT
            }
        history = data[chat_id]["history"]
        history.extend(new_messages)
        # Ограничиваем размер
        max_messages = MAX_HISTORY_PER_CHAT * 2
        if len(history) > max_messages:
            data[chat_id]["history"] = history[-max_messages:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")
    _pending_updates.clear()

async def _periodic_save():
    """Фоновая задача, запускаемая при старте бота."""
    while True:
        await asyncio.sleep(_SAVE_INTERVAL)
        if _pending_updates:
            await asyncio.to_thread(_merge_and_save)

def start_periodic_save():
    """Запустить фоновое сохранение. Вызвать при старте бота."""
    global _save_task
    if _save_task is None or _save_task.done():
        _save_task = asyncio.create_task(_periodic_save())

def stop_periodic_save():
    """Остановить фоновое сохранение и принудительно сохранить остатки."""
    global _save_task
    if _save_task and not _save_task.done():
        _save_task.cancel()
    if _pending_updates:
        _merge_and_save()

# --- Остальные функции (без изменений, кроме add_message_to_history) ---
def load_chat_data():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                else:
                    logger.warning("Файл истории повреждён. Создаю новый.")
                    return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}. Создаю новый файл.")
            return {}
    return {}

def save_chat_data(data: dict):
    """Синхронное сохранение (используется только для немедленных изменений: system_prompt, temperature и т.п.)."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")

def get_chat_data(chat_id: str) -> dict:
    data = load_chat_data()
    if chat_id not in data:
        data[chat_id] = {
            "system_prompt": None,
            "history": [],
            "temperature": DEFAULT_TEMPERATURE,
            "num_predict": DEFAULT_NUM_PREDICT
        }
        save_chat_data(data)
    return data[chat_id]

def set_system_prompt(chat_id: str, prompt: str | None):
    data = load_chat_data()
    if chat_id not in data:
        data[chat_id] = {
            "system_prompt": None,
            "history": [],
            "temperature": DEFAULT_TEMPERATURE,
            "num_predict": DEFAULT_NUM_PREDICT
        }
    data[chat_id]["system_prompt"] = prompt
    save_chat_data(data)

def set_temperature(chat_id: str, temp: float):
    data = load_chat_data()
    if chat_id not in data:
        data[chat_id] = {
            "system_prompt": None,
            "history": [],
            "temperature": DEFAULT_TEMPERATURE,
            "num_predict": DEFAULT_NUM_PREDICT
        }
    data[chat_id]["temperature"] = temp
    save_chat_data(data)

def set_num_predict(chat_id: str, num: int):
    data = load_chat_data()
    if chat_id not in data:
        data[chat_id] = {
            "system_prompt": None,
            "history": [],
            "temperature": DEFAULT_TEMPERATURE,
            "num_predict": DEFAULT_NUM_PREDICT
        }
    data[chat_id]["num_predict"] = num
    save_chat_data(data)

def clear_history(chat_id: str):
    data = load_chat_data()
    if chat_id in data:
        if isinstance(data[chat_id], dict):
            data[chat_id]["history"] = []
        else:
            data[chat_id] = {
                "system_prompt": None,
                "history": [],
                "temperature": DEFAULT_TEMPERATURE,
                "num_predict": DEFAULT_NUM_PREDICT
            }
        save_chat_data(data)

def add_message_to_history(chat_id: str, role: str, content: str):
    """Добавляет сообщение в очередь на периодическую запись."""
    new_msg = {"role": role, "content": content, "time": datetime.now().isoformat()}
    if chat_id not in _pending_updates:
        _pending_updates[chat_id] = []
    _pending_updates[chat_id].append(new_msg)
    # Если накопилось слишком много сообщений (например > 20), сохраняем немедленно
    if len(_pending_updates[chat_id]) > MAX_HISTORY_PER_CHAT:
        asyncio.create_task(asyncio.to_thread(_merge_and_save))

def build_prompt(chat_id: str, current_user_msg: str) -> str:
    chat_data = get_chat_data(chat_id)
    system_prompt = chat_data.get("system_prompt")
    history = chat_data.get("history", [])

    prompt_parts = []
    if system_prompt:
        prompt_parts.append(f"<|im_start|>system\n{system_prompt}<|im_end|>")

    for msg in history:
        role = msg["role"]
        content = msg["content"]
        prompt_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")

    prompt_parts.append(f"<|im_start|>user\n{current_user_msg}<|im_end|>")
    prompt_parts.append("<|im_start|>assistant\n")

    return "\n".join(prompt_parts)