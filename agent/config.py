# ============================================================
# agent/config.py
# Konfigurasi global JARVIS V5
# API keys dibaca dari .env (tidak di-push ke GitHub)
# ============================================================

import os
from pathlib import Path

# Load .env otomatis jika ada
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv opsional, fallback ke os.environ

# ── Direktori Kerja ──────────────────────────────────────────
# WORK_DIR = root folder project (D:\agent_ai\)
WORK_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Ollama LLM Backend ───────────────────────────────────────
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str    = "deepseek-r1:7b"       # Model utama
OLLAMA_FALLBACK: str = "llama3.1:8b"          # Model cadangan jika utama tidak ada
OLLAMA_TIMEOUT: int  = 120                     # Timeout request dalam detik

# ── API Keys Eksternal ───────────────────────────────────────
# Dibaca dari .env (lihat .env di root project)
TAVILY_API_KEY: str  = os.environ.get("TAVILY_API_KEY", "")
SHODAN_API_KEY: str  = os.environ.get("SHODAN_API_KEY", "")

# ── ReAct Agent ──────────────────────────────────────────────
MAX_STEPS: int = 8          # Maksimum langkah THINK→ACT→OBS per request
MAX_FILE_READ: int = 8000   # Maksimum karakter saat membaca file

# ── Server ───────────────────────────────────────────────────
SERVER_HOST: str = "0.0.0.0"
SERVER_PORT: int = 7432

# ── Path Helper ──────────────────────────────────────────────
def resolve_path(path: str) -> str:
    """
    Konversi path relatif menjadi absolut berdasarkan WORK_DIR.
    Jika path sudah absolut, kembalikan apa adanya.

    Args:
        path: Path string yang mungkin relatif atau absolut

    Returns:
        Path absolut sebagai string
    """
    if not path:
        return WORK_DIR
    if os.path.isabs(path):
        return path
    return os.path.join(WORK_DIR, path)
