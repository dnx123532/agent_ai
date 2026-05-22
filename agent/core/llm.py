# ============================================================
# agent/core/llm.py
# Ollama LLM Client untuk JARVIS V5
# Mendukung streaming token-by-token untuk response cepat
# ============================================================

import json
import requests
from typing import Optional, Generator, Callable

from agent.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_FALLBACK,
    OLLAMA_TIMEOUT,
)

# Tipe pesan chat
Message = dict  # {"role": "user"|"assistant"|"system", "content": str}


def list_models() -> list[str]:
    """Ambil daftar model yang tersedia di Ollama lokal."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


def is_ollama_running() -> bool:
    """Cek apakah Ollama server sedang berjalan."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def pick_model() -> str:
    """
    Pilih model terbaik yang tersedia.
    Prioritas: OLLAMA_MODEL -> OLLAMA_FALLBACK -> model pertama.
    """
    available = list_models()
    for model in available:
        if OLLAMA_MODEL in model or model in OLLAMA_MODEL:
            return model
    for model in available:
        if OLLAMA_FALLBACK in model or model in OLLAMA_FALLBACK:
            return model
    return available[0] if available else OLLAMA_MODEL


# ── Non-streaming (untuk internal ReAct JSON parsing) ────────
def chat(
    messages: list[Message],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """
    Kirim pesan ke Ollama, tunggu respons penuh.
    Dipakai untuk parsing JSON di ReAct loop.

    Returns:
        Respons teks lengkap dari LLM
    """
    if not is_ollama_running():
        raise ConnectionError("Ollama tidak berjalan! Jalankan: ollama serve")

    active_model = model or pick_model()

    payload = {
        "model":   active_model,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": temperature, "num_predict": max_tokens},
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    except requests.exceptions.Timeout:
        raise RuntimeError(f"Timeout setelah {OLLAMA_TIMEOUT}s")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP Error Ollama: {e}")
    except KeyError:
        raise RuntimeError(f"Format respons tidak dikenali: {resp.text[:200]}")
    except Exception as e:
        raise RuntimeError(f"Error chat: {e}")


# ── STREAMING — token by token ────────────────────────────────
def chat_stream(
    messages: list[Message],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """
    Stream respons Ollama token per token menggunakan NDJSON streaming.
    Yield setiap token string segera saat diterima dari model.

    Berguna untuk:
    - Menampilkan jawaban secara real-time ke user
    - Memberikan feeling "cepat" meski total waktu sama

    Yields:
        String token satu per satu
    """
    if not is_ollama_running():
        raise ConnectionError("Ollama tidak berjalan!")

    active_model = model or pick_model()

    payload = {
        "model":    active_model,
        "messages": messages,
        "stream":   True,  # Aktifkan streaming Ollama
        "options":  {"temperature": temperature, "num_predict": max_tokens},
    }

    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            stream=True,       # HTTP streaming
            timeout=OLLAMA_TIMEOUT,
        ) as resp:
            resp.raise_for_status()

            # Ollama streaming pakai NDJSON — satu JSON per baris
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue

                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                # Ambil token dari respons
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token

                # Cek apakah sudah selesai
                if data.get("done", False):
                    break

    except requests.exceptions.Timeout:
        raise RuntimeError(f"Timeout streaming setelah {OLLAMA_TIMEOUT}s")
    except Exception as e:
        raise RuntimeError(f"Error streaming: {e}")


def collect_stream(
    messages: list[Message],
    model: Optional[str] = None,
    temperature: float = 0.3,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Kumpulkan semua token streaming menjadi string penuh.
    Sambil mengumpulkan, panggil callback on_token untuk setiap token.

    Digunakan di ReAct loop: streaming ke frontend sambil tetap
    mendapatkan full text untuk parsing JSON.

    Args:
        messages:   List pesan chat
        model:      Override nama model
        temperature: Kreativitas LLM
        on_token:   Callback dipanggil tiap token (opsional)
                    Signature: on_token(token: str) -> None

    Returns:
        String lengkap dari semua token yang dikumpulkan
    """
    full_text = ""
    for token in chat_stream(messages, model=model, temperature=temperature):
        full_text += token
        if on_token:
            try:
                on_token(token)
            except Exception:
                pass  # Jangan stop streaming karena callback error
    return full_text


def chat_with_retry(
    messages: list[Message],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    retries: int = 2,
) -> str:
    """Wrapper chat() dengan retry otomatis jika gagal."""
    available_models = list_models()

    # Urutkan: model utama -> fallback -> sisanya
    ordered = []
    for m in available_models:
        if OLLAMA_MODEL in m:
            ordered.insert(0, m)
        elif OLLAMA_FALLBACK in m:
            ordered.append(m)
    for m in available_models:
        if m not in ordered:
            ordered.append(m)
    available_models = ordered or available_models or [OLLAMA_MODEL]

    last_error = None
    attempts = min(retries + 1, len(available_models))

    for i in range(attempts):
        try_model = available_models[i]
        try:
            return chat(messages, model=try_model, temperature=temperature, max_tokens=max_tokens)
        except RuntimeError as e:
            last_error = e
            continue

    raise RuntimeError(f"Semua {attempts} percobaan gagal. Error: {last_error}")
