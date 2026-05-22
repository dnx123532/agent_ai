@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║      JARVIS V5 — Setup Dependencies      ║
echo  ╚══════════════════════════════════════════╝
echo.

echo [1/4] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] pip install gagal! Pastikan Python dan pip sudah terinstall.
    pause
    exit /b 1
)

echo.
echo [2/4] Checking Ollama installation...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama tidak ditemukan di PATH.
    echo        Download dari: https://ollama.com/download
) else (
    echo [OK] Ollama ditemukan.
)

echo.
echo [3/4] Checking available models...
ollama list 2>nul || echo [WARN] Ollama tidak berjalan. Jalankan 'ollama serve' dulu.

echo.
echo [4/4] Checking deepseek-r1:7b...
ollama list 2>nul | findstr "deepseek-r1" >nul
if %errorlevel% neq 0 (
    echo [INFO] Model deepseek-r1:7b belum ada. Mau download sekarang? (ini ~4.7 GB)
    echo        Jalankan manual: ollama pull deepseek-r1:7b
) else (
    echo [OK] deepseek-r1:7b tersedia!
)

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   Setup selesai! Jalankan start.bat      ║
echo  ╚══════════════════════════════════════════╝
echo.
pause
