# ============================================================
# server/app.py
# FastAPI server JARVIS V5
# WebSocket /ws  → streaming real-time (utama)
# POST /chat     → SSE fallback
# GET /status    → cek Ollama
# GET /          → frontend
# ============================================================

import os
import sys
import json
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from agent.config import SERVER_HOST, SERVER_PORT
from agent.core.llm import is_ollama_running, list_models, pick_model
from agent.core.react_agent import run_agent, run_agent_ws
from server.models import ChatRequest, ChatResponse, StatusResponse

# ── Inisialisasi FastAPI ─────────────────────────────────────
app = FastAPI(
    title="JARVIS V5",
    description="AI Assistant lokal — Ollama + ReAct + WebSocket streaming",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = ROOT_DIR / "frontend"


# ════════════════════════════════════════════════════════════
# STATIC FILES
# ════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve halaman utama."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>JARVIS V5</h1><p>Frontend tidak ditemukan.</p>")
    return FileResponse(str(index_path))


@app.get("/static/{filename}")
async def serve_static(filename: str):
    """Serve file CSS, JS, aset statis."""
    file_path = FRONTEND_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' tidak ditemukan.")

    ext_to_mime = {
        ".css": "text/css", ".js": "application/javascript",
        ".png": "image/png", ".jpg": "image/jpeg",
        ".ico": "image/x-icon", ".svg": "image/svg+xml",
    }
    mime = ext_to_mime.get(file_path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(file_path), media_type=mime)


# ════════════════════════════════════════════════════════════
# STATUS
# ════════════════════════════════════════════════════════════

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Cek status Ollama dan model yang tersedia."""
    running = is_ollama_running()
    return StatusResponse(
        ollama_running=running,
        models=list_models() if running else [],
        active_model=pick_model() if running else "N/A",
        server_version="5.0.0",
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "JARVIS V5"}


# ════════════════════════════════════════════════════════════
# WEBSOCKET — streaming real-time (endpoint utama)
# ════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint untuk chat streaming real-time.

    Protocol:
    Client -> Server:
        {"message": "pertanyaan user"}

    Server -> Client (stream events):
        {"type": "thinking",  "step": 1}
        {"type": "step",      "step_type": "THINK", "thought": "...", "action": "..."}
        {"type": "step",      "step_type": "ACT",   "tool": "...",    "input": "..."}
        {"type": "step",      "step_type": "OBS",   "tool": "...",    "result": "..."}
        {"type": "token",     "content": "abc"}   <- final answer token by token
        {"type": "done",      "total_steps": N}
        {"type": "error",     "message": "..."}
    """
    await ws.accept()

    try:
        while True:
            # Terima pesan dari client
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=300)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
                continue

            message = data.get("message", "").strip()
            if not message:
                await ws.send_json({"type": "error", "message": "Pesan kosong."})
                continue

            # Cek Ollama
            if not is_ollama_running():
                await ws.send_json({
                    "type":    "error",
                    "message": "Ollama tidak berjalan. Jalankan: ollama serve"
                })
                continue

            # Jalankan agent di thread pool agar tidak block event loop
            # Streaming via asyncio.Queue — bridge antara sync generator dan async WS
            event_queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def agent_thread():
                """Thread worker: jalankan agent, masukkan event ke queue."""
                try:
                    for event in run_agent_ws(message):
                        # Thread-safe: put ke asyncio queue
                        loop.call_soon_threadsafe(event_queue.put_nowait, event)
                except Exception as e:
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait,
                        {"type": "error", "message": str(e)}
                    )
                finally:
                    # Sentinel untuk sinyal selesai
                    loop.call_soon_threadsafe(event_queue.put_nowait, None)

            # Jalankan agent di background thread
            thread = asyncio.get_event_loop().run_in_executor(None, agent_thread)

            # Relay events dari queue ke WebSocket
            done = False
            while not done:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "error", "message": "Agent timeout."})
                    break

                # None = sentinel, agent selesai
                if event is None:
                    done = True
                    break

                # Kirim event ke client
                await ws.send_json(event)

                # Jika sudah done dari agent sendiri, stop
                if event.get("type") == "done":
                    done = True

            await thread  # Pastikan thread selesai

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
# POST /chat — SSE fallback (untuk klien yang tidak support WS)
# ════════════════════════════════════════════════════════════

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Endpoint chat via SSE streaming atau JSON biasa."""
    if not is_ollama_running():
        return JSONResponse(status_code=503, content={
            "error": "Ollama tidak berjalan", "success": False
        })

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Pesan kosong.")

    if request.stream:
        # SSE streaming
        async def sse_generator():
            loop = asyncio.get_event_loop()

            def run_sync():
                return list(run_agent_ws(message))

            events = await loop.run_in_executor(None, run_sync)
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming: tunggu selesai
    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_agent, message)
        return ChatResponse(
            response=result.get("answer", ""),
            steps=result.get("steps", []),
            success=result.get("success", True),
            model=pick_model(),
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "success": False})


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    print("=" * 42)
    print("   JARVIS V5 - Starting Server")
    print("=" * 42)
    print(f"  URL      : http://localhost:{SERVER_PORT}")
    print(f"  WebSocket: ws://localhost:{SERVER_PORT}/ws")
    print(f"  Model    : {pick_model()}")
    ollama_ok = is_ollama_running()
    print(f"  Ollama   : {'Running' if ollama_ok else 'OFFLINE'}")
    print("=" * 42)

    if not ollama_ok:
        print("[WARN] Ollama offline! Jalankan: ollama serve")

    uvicorn.run(
        "server.app:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info",
    )
