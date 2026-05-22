# ============================================================
# agent/core/llm.py
# Ollama LLM Client untuk JARVIS V5
# Menangani koneksi, request, fallback model, dan error
# ============================================================

import json
import requests
from typing import Optional

from agent.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_FALLBACK,
    OLLAMA_TIMEOUT,
)


# ── Tipe pesan chat ──────────────────────────────────────────
Message = dict  # {"role": "user"|"assistant"|"system", "content": str}


def list_models() -> list[str]:
    """
    Ambil daftar model yang tersedia di Ollama lokal.

    Returns:
        List nama model (misal: ["deepseek-r1:7b", "llama3.1:8b"])
        Kembalikan list kosong jika Ollama tidak berjalan.
    """
    try:
        resp = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def is_ollama_running() -> bool:
    """
    Cek apakah Ollama server sedang berjalan.

    Returns:
        True jika Ollama aktif dan merespons
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def pick_model() -> str:
    """
    Pilih model terbaik yang tersedia.
    Prioritas: OLLAMA_MODEL → OLLAMA_FALLBACK → model pertama yang ada.

    Returns:
        Nama model yang akan digunakan
    """
    available = list_models()

    # Cek apakah model utama tersedia (bisa partial match)
    for model in available:
        if OLLAMA_MODEL in model or model in OLLAMA_MODEL:
            return model

    # Cek fallback
    for model in available:
        if OLLAMA_FALLBACK in model or model in OLLAMA_FALLBACK:
            return model

    # Ambil model pertama yang ada
    if available:
        return available[0]

    # Kembalikan default meski mungkin gagal
    return OLLAMA_MODEL


def chat(
    messages: list[Message],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Kirim pesan ke Ollama dan dapatkan respons teks.

    Args:
        messages:    List pesan dalam format [{"role": ..., "content": ...}]
        model:       Override nama model (opsional, default dari config)
        temperature: Kreativitas respons (0.0 = deterministik, 1.0 = kreatif)
        max_tokens:  Batas panjang output token

    Returns:
        Respons teks dari LLM sebagai string

    Raises:
        ConnectionError: Jika Ollama tidak berjalan
        RuntimeError:    Jika request gagal setelah retry
    """
    # Pastikan Ollama aktif
    if not is_ollama_running():
        raise ConnectionError(
            "Ollama tidak berjalan! Jalankan: ollama serve"
        )

    # Pilih model
    active_model = model or pick_model()

    # Bangun payload request
    payload = {
        "model": active_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # Ekstrak teks dari respons Ollama
        return data["message"]["content"]

    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Timeout setelah {OLLAMA_TIMEOUT}s — "
            "coba model lebih kecil atau naikkan OLLAMA_TIMEOUT"
        )
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP Error dari Ollama: {e}")
    except KeyError:
        raise RuntimeError(
            f"Format respons Ollama tidak dikenali: {resp.text[:300]}"
        )
    except Exception as e:
        raise RuntimeError(f"Error saat chat dengan Ollama: {e}")


def chat_with_retry(
    messages: list[Message],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    retries: int = 2,
) -> str:
    """
    Wrapper chat() dengan retry otomatis.
    Jika model utama gagal, coba model berikutnya yang tersedia.

    Args:
        messages:    List pesan chat
        model:       Override nama model (opsional)
        temperature: Kreativitas respons
        max_tokens:  Batas panjang output
        retries:     Jumlah percobaan ulang

    Returns:
        Respons teks dari LLM
    """
    available_models = list_models()
    # Tambahkan model pilihan di depan jika ada
    if model and model not in available_models:
        available_models.insert(0, model)
    elif not model:
        # Urutkan: model utama → fallback → sisanya
        ordered = []
        for m in available_models:
            if OLLAMA_MODEL in m:
                ordered.insert(0, m)
            elif OLLAMA_FALLBACK in m:
                ordered.append(m)
        for m in available_models:
            if m not in ordered:
                ordered.append(m)
        available_models = ordered or available_models

    last_error = None
    attempts = min(retries + 1, len(available_models)) if available_models else retries + 1

    for i in range(attempts):
        try_model = available_models[i] if i < len(available_models) else (model or OLLAMA_MODEL)
        try:
            return chat(messages, model=try_model, temperature=temperature, max_tokens=max_tokens)
        except RuntimeError as e:
            last_error = e
            continue

    raise RuntimeError(
        f"Semua percobaan gagal setelah {attempts} kali. Error terakhir: {last_error}"
    )
