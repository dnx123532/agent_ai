# ============================================================
# server/models.py
# Pydantic models untuk request dan response API — JARVIS V5
# ============================================================

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Request Models ───────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request body untuk endpoint POST /chat"""
    message: str = Field(
        ...,
        description="Pesan atau instruksi dari user",
        min_length=1,
        max_length=10000,
    )
    stream: bool = Field(
        default=True,
        description="Gunakan streaming response (SSE) atau tunggu selesai"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Tampilkan isi folder D:/agent_ai",
                "stream": True,
            }
        }


# ── Response Models ──────────────────────────────────────────

class StepModel(BaseModel):
    """Satu langkah dalam ReAct loop (THINK / ACT / OBS / ANSWER)"""
    step:         int          = Field(...,  description="Nomor langkah")
    type:         str          = Field(...,  description="Tipe: THINK, ACT, OBS, ANSWER")
    thought:      Optional[str] = Field(None, description="Pikiran LLM pada langkah ini")
    action:       Optional[str] = Field(None, description="Nama tool yang dipanggil")
    action_input: Optional[Any] = Field(None, description="Parameter input tool")
    result:       Optional[str] = Field(None, description="Hasil observasi dari tool")
    answer:       Optional[str] = Field(None, description="Jawaban final")


class ChatResponse(BaseModel):
    """Response body untuk endpoint POST /chat"""
    response: str = Field(..., description="Jawaban final dari JARVIS")
    steps:    list[StepModel] = Field(
        default_factory=list,
        description="Semua langkah ReAct yang dieksekusi"
    )
    success:  bool = Field(default=True, description="Apakah agent berhasil menyelesaikan task")
    model:    Optional[str] = Field(None, description="Model LLM yang digunakan")

    class Config:
        json_schema_extra = {
            "example": {
                "response": "Isi folder D:/agent_ai:\n📂 agent/\n📄 config.py",
                "steps": [
                    {
                        "step": 1,
                        "type": "THINK",
                        "thought": "User ingin melihat isi folder",
                        "action": "list_dir",
                        "action_input": {"path": "D:/agent_ai"},
                    }
                ],
                "success": True,
                "model": "deepseek-r1:7b",
            }
        }


class StatusResponse(BaseModel):
    """Response untuk endpoint GET /status"""
    ollama_running: bool = Field(...,  description="Status Ollama server")
    models:         list[str] = Field(default_factory=list, description="Daftar model tersedia")
    active_model:   str  = Field(...,  description="Model yang sedang aktif digunakan")
    server_version: str  = Field(default="5.0.0", description="Versi JARVIS")

    class Config:
        json_schema_extra = {
            "example": {
                "ollama_running": True,
                "models": ["deepseek-r1:7b"],
                "active_model": "deepseek-r1:7b",
                "server_version": "5.0.0",
            }
        }


class ErrorResponse(BaseModel):
    """Response untuk error"""
    error:   str = Field(..., description="Pesan error")
    detail:  Optional[str] = Field(None, description="Detail error tambahan")
    success: bool = Field(default=False)
