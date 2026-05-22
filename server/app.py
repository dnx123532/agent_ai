# ============================================================
# server/app.py
# FastAPI server untuk JARVIS V5
# Routes: /chat, /status, / (frontend), /static/{file}
# ============================================================

import os
import sys
import json
import asyncio
from pathlib import Path

# Tambahkan root project ke sys.path agar import agent/* berjalan
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import (
    HTMLResponse, FileResponse, StreamingResponse, JSONResponse
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent.config import SERVER_HOST, SERVER_PORT
from agent.core.llm import is_ollama_running, list_models, pick_model
from agent.core.react_agent import run_agent, run_agent_stream
from server.models import ChatRequest, ChatResponse, StatusResponse, ErrorResponse

# ── Inisialisasi FastAPI ─────────────────────────────────────
app = FastAPI(
    title="JARVIS V5",
    description="AI Assistant lokal berbasis Ollama + ReAct Agent",
    version="5.0.0",
)

# ── CORS — izinkan semua origin (lokal) ─────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Path frontend ────────────────────────────────────────────
FRONTEND_DIR = ROOT_DIR / "frontend"


# ════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve halaman utama JARVIS frontend."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>JARVIS V5</h1><p>Frontend belum tersedia. Pastikan frontend/index.html ada.</p>",
            status_code=200,
        )
    return FileResponse(str(index_path))


@app.get("/static/{filename}")
async def serve_static(filename: str):
    """Serve file CSS, JS, dan aset statis lainnya."""
    file_path = FRONTEND_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' tidak ditemukan.")

    # Tentukan content type
    content_type_map = {
        ".css":  "text/css",
        ".js":   "application/javascript",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".ico":  "image/x-icon",
        ".svg":  "image/svg+xml",
        ".woff": "font/woff",
        ".woff2":"font/woff2",
    }
    suffix       = file_path.suffix.lower()
    content_type = content_type_map.get(suffix, "application/octet-stream")

    return FileResponse(str(file_path), media_type=content_type)


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Cek status sistem JARVIS V5:
    - Apakah Ollama berjalan
    - Model yang tersedia
    - Model aktif
    """
    running = is_ollama_running()
    models  = list_models() if running else []
    active  = pick_model() if running else "N/A"

    return StatusResponse(
        ollama_running=running,
        models=models,
        active_model=active,
        server_version="5.0.0",
    )


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint utama untuk percakapan dengan JARVIS.

    - Jika stream=True: kembalikan Server-Sent Events (SSE) real-time
    - Jika stream=False: tunggu selesai, kembalikan JSON biasa

    Request body:
        {"message": "...", "stream": true}

    Response (non-stream):
        {"response": "...", "steps": [...], "success": true}
    """
    # Cek Ollama sebelum proses
    if not is_ollama_running():
        return JSONResponse(
            status_code=503,
            content={
                "error":   "Ollama tidak berjalan",
                "detail":  "Jalankan 'ollama serve' lalu coba lagi.",
                "success": False,
            },
        )

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    # ── Mode Streaming (SSE) ──────────────────────────────────
    if request.stream:
        async def event_generator():
            """Generator untuk Server-Sent Events."""
            try:
                # Jalankan agent di thread terpisah (blocking → async)
                loop = asyncio.get_event_loop()

                def run_streaming():
                    return list(run_agent_stream(message))

                steps = await loop.run_in_executor(None, run_streaming)

                for step_data in steps:
                    # Kirim setiap langkah sebagai SSE event
                    yield f"data: {json.dumps(step_data, ensure_ascii=False)}\n\n"

            except Exception as e:
                error_data = {"type": "error", "message": str(e)}
                yield f"data: {json.dumps(error_data)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Mode Non-Streaming ────────────────────────────────────
    else:
        try:
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_agent, message)

            active_model = pick_model()

            return ChatResponse(
                response=result.get("answer", ""),
                steps=result.get("steps", []),
                success=result.get("success", True),
                model=active_model,
            )

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error":   "Internal server error",
                    "detail":  str(e),
                    "success": False,
                },
            )


# ── Health check ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "JARVIS V5"}


# ════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    print("╔══════════════════════════════════════╗")
    print("║          JARVIS V5 — Starting        ║")
    print("╠══════════════════════════════════════╣")
    print(f"║  URL  : http://localhost:{SERVER_PORT}       ║")
    print(f"║  Model: {pick_model():<29}║")

    ollama_ok = is_ollama_running()
    status = "✅ Running" if ollama_ok else "❌ Offline"
    print(f"║  Ollama: {status:<28}║")
    print("╚══════════════════════════════════════╝")

    if not ollama_ok:
        print("\n⚠️  PERINGATAN: Ollama tidak terdeteksi!")
        print("   Jalankan: ollama serve")
        print("   Lalu pastikan model tersedia: ollama pull deepseek-r1:7b\n")

    uvicorn.run(
        "server.app:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info",
    )
