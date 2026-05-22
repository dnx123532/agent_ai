@echo off
echo.
echo ============================================
echo   JARVIS V5 - Setup Dependencies
echo ============================================
echo.

echo [1/4] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] pip install failed!
    echo Make sure Python and pip are installed.
    pause
    exit /b 1
)

echo.
echo [2/4] Checking Ollama...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not found in PATH.
    echo        Download: https://ollama.com/download
) else (
    echo [OK] Ollama found.
)

echo.
echo [3/4] Checking available models...
ollama list 2>nul

echo.
echo [4/4] Checking deepseek-r1:7b...
ollama list 2>nul | findstr "deepseek-r1" >nul
if %errorlevel% neq 0 (
    echo [INFO] deepseek-r1:7b not found.
    echo        Run manually: ollama pull deepseek-r1:7b
) else (
    echo [OK] deepseek-r1:7b is available!
)

echo.
echo ============================================
echo   Setup complete! Run: .\start.bat
echo ============================================
echo.
pause
