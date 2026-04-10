#!/usr/bin/env python3
"""
Мониторинг Cloudflare WARP. Только переподключение при проблемах.
"""

import subprocess
import time
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import WARP_LOG_FILE

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(WARP_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("WARP-Monitor")

CHECK_INTERVAL = 2
TARGET_HOST = "8.8.8.8"
PING_THRESHOLD_MS = 200
FAIL_THRESHOLD = 2
SUCCESS_RESET = 2
RECONNECT_PAUSE = 15

def check_internet():
    try:
        cmd = ["powershell", "-Command", f"Test-Connection -ComputerName {TARGET_HOST} -Count 1 -Quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if result.returncode != 0 or result.stdout.strip() != "True":
            return False, None

        cmd_time = ["powershell", "-Command", f"(Test-Connection -ComputerName {TARGET_HOST} -Count 1).ResponseTime"]
        result_time = subprocess.run(cmd_time, capture_output=True, text=True, timeout=3)
        if result_time.returncode != 0:
            return False, None

        ping_ms = float(result_time.stdout.strip())
        ok = ping_ms <= PING_THRESHOLD_MS
        return ok, ping_ms
    except Exception as e:
        logger.error(f"Ping error: {e}")
        return False, None

def reconnect_warp():
    logger.warning("Reconnecting WARP...")
    try:
        subprocess.run(["warp-cli", "disconnect"], capture_output=True, timeout=5)
        time.sleep(2)
        subprocess.run(["warp-cli", "connect"], capture_output=True, timeout=5)
        logger.info("WARP reconnected.")
    except Exception as e:
        logger.error(f"Reconnect failed: {e}")

def monitor():
    logger.info(f"Monitor started (interval {CHECK_INTERVAL}s, threshold {PING_THRESHOLD_MS}ms)")
    fail_count = 0
    success_streak = 0

    while True:
        ok, ping_ms = check_internet()

        if ok:
            success_streak += 1
            if success_streak >= SUCCESS_RESET and fail_count > 0:
                logger.info(f"Connection restored. Ping: {ping_ms:.0f} ms")
                fail_count = 0
                success_streak = 0
        else:
            success_streak = 0
            fail_count += 1
            if ping_ms is not None:
                logger.warning(f"High ping: {ping_ms:.0f} ms (>{PING_THRESHOLD_MS}) — issue {fail_count}/{FAIL_THRESHOLD}")
            else:
                logger.warning(f"Packet loss — issue {fail_count}/{FAIL_THRESHOLD}")

            if fail_count >= FAIL_THRESHOLD:
                logger.error(f"{fail_count} issues, reconnecting WARP...")
                reconnect_warp()
                time.sleep(RECONNECT_PAUSE)
                fail_count = 0
                success_streak = 0

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        logger.info("Monitor stopped.")