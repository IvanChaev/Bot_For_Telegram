import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent

env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

OLLAMA_URL = "http://localhost:11434"
OLLAMA_GENERATE = f"{OLLAMA_URL}/api/generate"
OLLAMA_TAGS = f"{OLLAMA_URL}/api/tags"

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")
MODEL_NAME = os.getenv("MODEL_NAME", "ААААААААААААААААААА НаЗвАнИе ВаШеЙ МОДЕЛИ В ЭТИХ КАВЫЧКАХ Ollama list в cmd ЧТОБЫ ПРОВЕРИТЬ")
CONTEXT_LENGTH = int(os.getenv("CONTEXT_LENGTH", "8192"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DELETE_COMMANDS = os.getenv("DELETE_COMMANDS", "false").lower() == "true"
VOICE_NAME = "ru-RU-DmitryNeural"

# Папки
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Файлы
HISTORY_FILE = DATA_DIR / "chat_history.json"
ALLOWED_USERS_FILE = DATA_DIR / "allowed_users.json"
GLOBAL_SETTINGS_FILE = DATA_DIR / "global_settings.json"
LOG_FILE = LOGS_DIR / "bot.log"
WARP_LOG_FILE = LOGS_DIR / "warp_monitor.log"
SUPERVISOR_LOG_FILE = LOGS_DIR / "supervisor.log"

MAX_HISTORY_PER_CHAT = 20
DEFAULT_TEMPERATURE = 0.7
DEFAULT_NUM_PREDICT = 384
GENERATION_TIMEOUT = 300

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле.")