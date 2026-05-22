@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║         JARVIS V5 — Starting...          ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  URL : http://localhost:7432
echo  Model : deepseek-r1:7b (via Ollama)
echo.

REM Tunggu sebentar lalu buka browser
timeout /t 2 /nobreak >nul
start "" "http://localhost:7432"

REM Jalankan server
python server/app.py

pause
