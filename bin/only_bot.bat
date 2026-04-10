@echo off
chcp 65001 >nul
title Telegram Bot

cd /d "%~dp0\.."

echo ======================================================
echo   Запуск Telegram Bot
echo ======================================================
echo.

python bot.py