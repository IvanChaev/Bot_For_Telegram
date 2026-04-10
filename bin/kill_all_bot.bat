@echo off
echo Завершение всех процессов python.exe и ollama.exe...
taskkill /F /IM python.exe
taskkill /F /IM pythonw.exe
taskkill /f /im ollama.exe
taskkill /f /im cmd.exe
echo Готово.
pause

