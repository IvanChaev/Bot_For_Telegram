@echo off
chcp 65001 >nul
title Telegram Bot Supervisor

cd /d "%~dp0\.."

echo ======================================================
echo   Запуск Telegram Bot с аварийным переподключением
echo   Логи пишутся в папку logs\
echo   Для остановки закрой это окно или нажми Ctrl+C
echo ======================================================
echo.

python src/supervisor.py