#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
from src.bot_app import main

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен вручную")