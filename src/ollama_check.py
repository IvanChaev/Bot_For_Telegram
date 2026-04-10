import subprocess
import sys
import time
import logging
import requests
from .config import OLLAMA_TAGS

logger = logging.getLogger(__name__)

def check_ollama_sync():
    try:
        resp = requests.get(OLLAMA_TAGS, timeout=2)
        if resp.status_code == 200:
            logger.info("Ollama сервер уже запущен")
            return True
    except:
        logger.warning("Ollama сервер не отвечает, пробую запустить...")
        try:
            if sys.platform == "win32":
                subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(10):
                time.sleep(1)
                try:
                    resp = requests.get(OLLAMA_TAGS, timeout=1)
                    if resp.status_code == 200:
                        logger.info("Ollama сервер успешно запущен")
                        return True
                except:
                    continue
            logger.error("Не удалось запустить Ollama сервер автоматически")
            return False
        except Exception as e:
            logger.error(f"Ошибка при запуске Ollama: {e}")
            return False
    return True