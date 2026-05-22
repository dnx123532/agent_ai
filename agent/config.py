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
    pass

# ── Direktori Kerja ──────────────────────────────────────────
WORK_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Provider LLM — "groq" atau "ollama" ──────────────────────
# Set LLM_PROVIDER=groq di .env untuk pakai Groq (cepat!)
# Set LLM_PROVIDER=ollama untuk pakai lokal
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "ollama").lower()

# ── Groq API ─────────────────────────────────────────────────
GROQ_API_KEY: str    = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL: str   = "https://api.groq.com/openai/v1"
GROQ_MODEL: str      = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT: int    = 60

# ── Ollama LLM Backend ───────────────────────────────────────
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str    = "deepseek-r1:7b"
OLLAMA_FALLBACK: str = "llama3.1:8b"
OLLAMA_TIMEOUT: int  = 120

# ── API Keys Eksternal ───────────────────────────────────────
TAVILY_API_KEY: str  = os.environ.get("TAVILY_API_KEY", "")
SHODAN_API_KEY: str  = os.environ.get("SHODAN_API_KEY", "")

# ── ReAct Agent ──────────────────────────────────────────────
MAX_STEPS: int     = 8
MAX_FILE_READ: int = 8000

# ── Server ───────────────────────────────────────────────────
SERVER_HOST: str = "0.0.0.0"
SERVER_PORT: int = 7432

# ── Path Helper ──────────────────────────────────────────────
def resolve_path(path: str) -> str:
    """Relatif -> absolut dari WORK_DIR, absolut dikembalikan apa adanya."""
    if not path:
        return WORK_DIR
    if os.path.isabs(path):
        return path
    return os.path.join(WORK_DIR, path)
