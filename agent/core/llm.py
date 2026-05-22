# ============================================================
# agent/core/llm.py
# LLM Client JARVIS V5 — support Groq & Ollama
# Auto-switch berdasarkan LLM_PROVIDER di .env
# Groq: 750+ tok/s  |  Ollama: lokal 100% offline
# ============================================================

import json
import requests
from typing import Optional, Generator, Callable

from agent.config import (
    LLM_PROVIDER,
    # Groq
    GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL, GROQ_TIMEOUT,
    # Ollama
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_FALLBACK, OLLAMA_TIMEOUT,
)

Message = dict  # {"role": "...", "content": "..."}


# ════════════════════════════════════════════════════════════
# PROVIDER INFO
# ════════════════════════════════════════════════════════════

def get_provider() -> str:
    """Return provider aktif: 'groq' atau 'ollama'."""
    if LLM_PROVIDER == "groq" and GROQ_API_KEY:
        return "groq"
    return "ollama"


def get_active_model() -> str:
    """Return nama model yang sedang aktif dipakai."""
    if get_provider() == "groq":
        return GROQ_MODEL
    return pick_ollama_model()


# ════════════════════════════════════════════════════════════
# OLLAMA HELPERS
# ════════════════════════════════════════════════════════════

def list_models() -> list[str]:
    """Daftar model Ollama yang tersedia."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def is_ollama_running() -> bool:
    try:
        return requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5).status_code == 200
    except Exception:
        return False


def pick_ollama_model() -> str:
    available = list_models()
    for m in available:
        if OLLAMA_MODEL in m or m in OLLAMA_MODEL:
            return m
    for m in available:
        if OLLAMA_FALLBACK in m or m in OLLAMA_FALLBACK:
            return m
    return available[0] if available else OLLAMA_MODEL


def pick_model() -> str:
    """Alias publik untuk get_active_model."""
    return get_active_model()


# ════════════════════════════════════════════════════════════
# GROQ — non-streaming
# ════════════════════════════════════════════════════════════

def _groq_chat(messages: list[Message], temperature: float = 0.3,
               max_tokens: int = 4096) -> str:
    """Kirim request ke Groq API, return full text."""
    if not GROQ_API_KEY:
        raise ConnectionError("GROQ_API_KEY kosong. Isi di .env")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "stream":      False,
    }
    try:
        resp = requests.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=headers, json=payload, timeout=GROQ_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Groq timeout setelah {GROQ_TIMEOUT}s")
    except requests.exceptions.HTTPError as e:
        body = ""
        try: body = e.response.json().get("error", {}).get("message", "")
        except Exception: pass
        raise RuntimeError(f"Groq HTTP error: {e} — {body}")
    except KeyError:
        raise RuntimeError(f"Format respons Groq tidak dikenali")
    except Exception as e:
        raise RuntimeError(f"Groq error: {e}")


# ════════════════════════════════════════════════════════════
# GROQ — streaming (SSE format)
# ════════════════════════════════════════════════════════════

def _groq_stream(messages: list[Message],
                 temperature: float = 0.7,
                 max_tokens: int = 4096) -> Generator[str, None, None]:
    """
    Stream token dari Groq via OpenAI-compatible SSE.
    Format: data: {"choices":[{"delta":{"content":"token"}}]}
    """
    if not GROQ_API_KEY:
        raise ConnectionError("GROQ_API_KEY kosong.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "stream":      True,
    }
    try:
        with requests.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=headers, json=payload,
            stream=True, timeout=GROQ_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data  = json.loads(data_str)
                    token = data["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Groq stream timeout setelah {GROQ_TIMEOUT}s")
    except Exception as e:
        raise RuntimeError(f"Groq stream error: {e}")


# ════════════════════════════════════════════════════════════
# OLLAMA — non-streaming
# ════════════════════════════════════════════════════════════

def _ollama_chat(messages: list[Message], model: Optional[str] = None,
                 temperature: float = 0.3, max_tokens: int = 4096) -> str:
    if not is_ollama_running():
        raise ConnectionError("Ollama tidak berjalan! Jalankan: ollama serve")
    active = model or pick_ollama_model()
    payload = {
        "model": active, "messages": messages, "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat",
                             json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama timeout setelah {OLLAMA_TIMEOUT}s")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


# ════════════════════════════════════════════════════════════
# OLLAMA — streaming (NDJSON)
# ════════════════════════════════════════════════════════════

def _ollama_stream(messages: list[Message], model: Optional[str] = None,
                   temperature: float = 0.7,
                   max_tokens: int = 4096) -> Generator[str, None, None]:
    if not is_ollama_running():
        raise ConnectionError("Ollama tidak berjalan!")
    active  = model or pick_ollama_model()
    payload = {
        "model": active, "messages": messages, "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        with requests.post(f"{OLLAMA_BASE_URL}/api/chat",
                           json=payload, stream=True, timeout=OLLAMA_TIMEOUT) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if not raw:
                    continue
                try:
                    data  = json.loads(raw)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        raise RuntimeError(f"Ollama stream error: {e}")


# ════════════════════════════════════════════════════════════
# PUBLIC API — otomatis pilih provider
# ════════════════════════════════════════════════════════════

def chat(messages: list[Message], model: Optional[str] = None,
         temperature: float = 0.3, max_tokens: int = 4096) -> str:
    """
    Kirim pesan ke LLM aktif (Groq / Ollama), tunggu full response.
    Dipakai untuk JSON parsing di ReAct loop.
    """
    if get_provider() == "groq":
        return _groq_chat(messages, temperature, max_tokens)
    return _ollama_chat(messages, model, temperature, max_tokens)


def chat_stream(messages: list[Message], model: Optional[str] = None,
                temperature: float = 0.7,
                max_tokens: int = 4096) -> Generator[str, None, None]:
    """
    Stream token dari LLM aktif (Groq / Ollama).
    Yield satu token (string) per iterasi.
    """
    if get_provider() == "groq":
        yield from _groq_stream(messages, temperature, max_tokens)
    else:
        yield from _ollama_stream(messages, model, temperature, max_tokens)


def collect_stream(messages: list[Message], model: Optional[str] = None,
                   temperature: float = 0.3,
                   on_token: Optional[Callable[[str], None]] = None) -> str:
    """
    Kumpulkan semua token streaming jadi string penuh.
    Sambil memanggil on_token callback untuk setiap token (untuk relay ke WS).
    """
    full = ""
    for token in chat_stream(messages, model=model, temperature=temperature):
        full += token
        if on_token:
            try:
                on_token(token)
            except Exception:
                pass
    return full


def chat_with_retry(messages: list[Message], model: Optional[str] = None,
                    temperature: float = 0.3, max_tokens: int = 4096,
                    retries: int = 2) -> str:
    """chat() dengan retry. Groq: retry dengan key yang sama. Ollama: coba model lain."""
    last_err = None
    for i in range(max(retries, 1)):
        try:
            return chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        except RuntimeError as e:
            last_err = e
            continue
    raise RuntimeError(f"Gagal setelah {retries} kali. Error: {last_err}")
