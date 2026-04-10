#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
import time
import sys
import threading
import logging
import signal
import atexit
from pathlib import Path

# Добавляем корневую папку в путь, чтобы импортировать config
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import SUPERVISOR_LOG_FILE, BASE_DIR

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(SUPERVISOR_LOG_FILE, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("Supervisor")

PROCESSES = [
    {"name": "WARP Monitor", "cmd": [sys.executable, str(Path(__file__).parent / "warp_monitor.py")], "process": None, "prefix": "[WARP]"},
    {"name": "Telegram Bot",  "cmd": [sys.executable, str(BASE_DIR / "bot.py")], "process": None, "prefix": "[BOT]"}
]

def read_output(proc, proc_info):
    for line in iter(proc.stdout.readline, ''):
        if line:
            logger.info(f"{proc_info['prefix']} {line.rstrip()}")

def start_process(proc_info):
    try:
        logger.info(f"Запуск {proc_info['name']}...")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            proc_info["cmd"],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            text=True,
            bufsize=1
        )
        proc_info["process"] = proc
        threading.Thread(target=read_output, args=(proc, proc_info), daemon=True).start()
        logger.info(f"{proc_info['name']} PID: {proc.pid}")
        return proc
    except Exception as e:
        logger.error(f"Ошибка запуска {proc_info['name']}: {e}")
        return None

def terminate_process(proc_info):
    proc = proc_info["process"]
    if proc is None:
        return
    try:
        logger.info(f"Остановка {proc_info['name']} (PID: {proc.pid})...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception as e:
        logger.error(f"Ошибка остановки {proc_info['name']}: {e}")
    finally:
        proc_info["process"] = None

def kill_all():
    for p in PROCESSES:
        terminate_process(p)

def cleanup():
    logger.info("Очистка процессов...")
    kill_all()

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda s, f: (cleanup(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s, f: (cleanup(), sys.exit(0)))

def main():
    logger.info("Супервизор запущен. Для выхода закройте окно или нажмите Ctrl+C.")
    restart_delay = 20
    error_delay = 5

    while True:
        # Запускаем отсутствующие процессы
        for p in PROCESSES:
            if p["process"] is None or p["process"].poll() is not None:
                start_process(p)

        time.sleep(10)

        any_failed = False
        for p in PROCESSES:
            proc = p["process"]
            if proc is None:
                any_failed = True
                continue
            retcode = proc.poll()
            if retcode is not None:
                logger.warning(f"{p['name']} завершился с кодом {retcode}")
                if retcode != 0:
                    any_failed = True
                p["process"] = None

        if any_failed:
            logger.error("Обнаружена проблема (процесс завершился с ошибкой), перезапуск через 5 сек...")
            kill_all()
            time.sleep(error_delay)
            logger.info(f"Перезапуск через {restart_delay} сек...")
            time.sleep(restart_delay)
        else:
            logger.debug("Все процессы работают стабильно")

if __name__ == "__main__":
    main()