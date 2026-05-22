@echo off
echo.
echo ============================================
echo   JARVIS V5 - Starting Server
echo ============================================
echo.
echo   URL   : http://localhost:7432
echo   Model : deepseek-r1:7b (Ollama)
echo.

timeout /t 2 /nobreak >nul
start "" "http://localhost:7432"

python server/app.py
pause
