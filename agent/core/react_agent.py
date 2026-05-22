# ============================================================
# agent/core/react_agent.py
# ReAct Agent Loop: THINK -> ACT -> OBSERVE
# Mendukung WebSocket streaming token-by-token
# Filter <think>...</think> dari deepseek-r1
# ============================================================

import re
import json
import queue
import threading
from typing import Any, Generator

from agent.config import MAX_STEPS
from agent.core.llm import chat_with_retry, collect_stream, pick_model
from agent.core.prompts import SYSTEM_PROMPT, format_observation, format_error

from agent.tools.file_tools   import list_dir, create_folder, save_text, read_file, move_file
from agent.tools.office_tools import create_docx, create_xlsx
from agent.tools.system_tools import system_info, list_processes, run_command
from agent.tools.web_tools    import web_search, open_browser
from agent.tools.intel_tools  import shodan_scan, intel_scan, generate_html_report

# ── Registry tools ───────────────────────────────────────────
TOOL_REGISTRY: dict[str, Any] = {
    "list_dir":             list_dir,
    "create_folder":        create_folder,
    "save_text":            save_text,
    "read_file":            read_file,
    "move_file":            move_file,
    "create_docx":          create_docx,
    "create_xlsx":          create_xlsx,
    "system_info":          system_info,
    "list_processes":       list_processes,
    "run_command":          run_command,
    "web_search":           web_search,
    "open_browser":         open_browser,
    "shodan_scan":          shodan_scan,
    "intel_scan":           intel_scan,
    "generate_html_report": generate_html_report,
}


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _strip_think_tags(text: str) -> str:
    """
    Hapus blok <think>...</think> dari output deepseek-r1.
    Model ini generate internal reasoning yang tidak perlu ditampilkan ke user.

    Args:
        text: Raw output dari LLM (mungkin berisi <think> blocks)

    Returns:
        Teks bersih tanpa blok think
    """
    # Hapus blok <think>...</think> (termasuk multiline)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)
    return cleaned.strip()


def _extract_json(text: str) -> dict:
    """
    Ekstrak JSON dari teks LLM yang mungkin mengandung markdown atau think tags.
    Robust terhadap code blocks, trailing comma, whitespace berlebih.
    """
    # Bersihkan think tags dulu
    text = _strip_think_tags(text).strip()

    # Coba parse langsung
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code block
    patterns = [
        r'```json\s*([\s\S]+?)\s*```',
        r'```\s*([\s\S]+?)\s*```',
        r'`(\{[\s\S]+?\})`',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Cari JSON dengan bracket matching
    brace, start = 0, None
    for i, ch in enumerate(text):
        if ch == '{':
            if start is None:
                start = i
            brace += 1
        elif ch == '}':
            brace -= 1
            if brace == 0 and start is not None:
                candidate = text[start:i+1]
                candidate = re.sub(r',(\s*[}\]])', r'\1', candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = None
                    brace = 0

    raise ValueError(f"Tidak ada JSON valid:\n{text[:400]}")


def _execute_tool(action: str, action_input: dict) -> str:
    """Eksekusi tool berdasarkan nama dan input."""
    if action not in TOOL_REGISTRY:
        available = ", ".join(TOOL_REGISTRY.keys())
        return f"Error: Tool '{action}' tidak ada. Tersedia: {available}"
    try:
        if not isinstance(action_input, dict):
            action_input = {}
        return str(TOOL_REGISTRY[action](**action_input))
    except TypeError as e:
        return f"Error parameter '{action}': {e}"
    except Exception as e:
        return f"Error '{action}': {e}"


# ════════════════════════════════════════════════════════════
# NON-STREAMING (untuk /chat non-stream)
# ════════════════════════════════════════════════════════════

def run_agent(user_message: str) -> dict:
    """Jalankan ReAct loop, return dict {answer, steps, success}."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]
    steps: list[dict] = []
    final_answer = ""

    for step_num in range(1, MAX_STEPS + 1):
        try:
            raw = chat_with_retry(messages, temperature=0.3)
        except Exception as e:
            return {"answer": f"Error Ollama: {e}", "steps": steps, "success": False}

        try:
            parsed = _extract_json(raw)
        except ValueError:
            return {"answer": _strip_think_tags(raw), "steps": steps, "success": True}

        thought      = parsed.get("thought", "")
        action       = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        steps.append({"step": step_num, "type": "THINK", "thought": thought,
                      "action": action, "action_input": action_input})

        if action == "final_answer":
            final_answer = action_input.get("answer", str(action_input)) \
                if isinstance(action_input, dict) else str(action_input)
            steps.append({"step": step_num, "type": "ANSWER", "answer": final_answer})
            break

        if not action:
            final_answer = thought or _strip_think_tags(raw)
            break

        steps.append({"step": step_num, "type": "ACT", "tool": action, "input": action_input})

        obs      = _execute_tool(action, action_input)
        obs_msg  = format_observation(action, obs)

        steps.append({"step": step_num, "type": "OBS", "tool": action, "result": obs[:500]})

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",      "content": obs_msg})
    else:
        obs_list     = [s["result"] for s in steps if s.get("type") == "OBS"]
        final_answer = "\n".join(obs_list[-3:]) if obs_list else "Selesai."

    return {"answer": final_answer, "steps": steps, "success": True}


# ════════════════════════════════════════════════════════════
# WEBSOCKET STREAMING — kirim token real-time
# ════════════════════════════════════════════════════════════

def run_agent_ws(user_message: str) -> Generator[dict, None, None]:
    """
    ReAct loop dengan WebSocket streaming.

    Alur:
    1. Setiap langkah THINK → yield event {"type":"step", "step_type":"THINK", ...}
    2. Setiap tool call → yield {"type":"step", "step_type":"ACT"/"OBS", ...}
    3. Final answer → stream token per token via {"type":"token", "content":"..."}
    4. Selesai → yield {"type":"done"}

    deepseek-r1 <think> blocks disembunyikan dari user tapi dipakai agent.

    Yields:
        Dict event untuk dikirim via WebSocket
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    for step_num in range(1, MAX_STEPS + 1):

        # ── Kumpulkan token sambil streaming think indicator ──
        think_tokens = []

        # Notify frontend: sedang thinking
        yield {"type": "thinking", "step": step_num}

        # Collect token-by-token, filter think untuk display
        # tapi tetap simpan full text untuk parsing JSON
        visible_buffer = ""
        think_depth    = 0

        def on_token(token: str) -> None:
            nonlocal think_depth, visible_buffer
            visible_buffer += token
            think_tokens.append(token)

        try:
            raw = collect_stream(messages, temperature=0.3, on_token=on_token)
        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return

        # Parse JSON dari full response (sudah di-strip think tags)
        try:
            parsed = _extract_json(raw)
        except ValueError:
            # Bukan JSON — stream sebagai final answer langsung
            clean = _strip_think_tags(raw)
            yield {"type": "step", "step_type": "THINK",
                   "step": step_num, "thought": "Jawaban langsung", "action": "final_answer"}
            yield from _stream_text(clean)
            yield {"type": "done"}
            return

        thought      = parsed.get("thought", "")
        action       = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        # Kirim step THINK ke frontend
        yield {
            "type":         "step",
            "step_type":    "THINK",
            "step":         step_num,
            "thought":      thought,
            "action":       action,
            "action_input": str(action_input)[:200] if action_input else "",
        }

        # ── Final answer → stream token ke user ──────────────
        if action == "final_answer":
            answer_text = action_input.get("answer", str(action_input)) \
                if isinstance(action_input, dict) else str(action_input)

            yield from _stream_text(answer_text)
            yield {"type": "done", "total_steps": step_num}
            return

        # Tidak ada action → treat sebagai jawaban
        if not action:
            clean = _strip_think_tags(raw)
            yield from _stream_text(clean)
            yield {"type": "done", "total_steps": step_num}
            return

        # ── ACT: eksekusi tool ────────────────────────────────
        yield {
            "type":      "step",
            "step_type": "ACT",
            "step":      step_num,
            "tool":      action,
            "input":     str(action_input)[:300],
        }

        obs     = _execute_tool(action, action_input)
        obs_msg = format_observation(action, obs)

        # ── OBS: kirim hasil tool ─────────────────────────────
        yield {
            "type":      "step",
            "step_type": "OBS",
            "step":      step_num,
            "tool":      action,
            "result":    obs[:500],
        }

        # Update conversation
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",      "content": obs_msg})

    # Habis MAX_STEPS
    yield {"type": "step", "step_type": "THINK", "step": MAX_STEPS,
           "thought": f"Batas {MAX_STEPS} langkah tercapai.", "action": "final_answer"}
    yield from _stream_text(f"Saya telah mencapai batas {MAX_STEPS} langkah.")
    yield {"type": "done", "total_steps": MAX_STEPS}


def _stream_text(text: str, chunk_size: int = 3) -> Generator[dict, None, None]:
    """
    Pecah teks menjadi chunk kecil dan yield sebagai token events.
    Membuat efek typewriter di frontend.

    Args:
        text:       Teks yang akan di-stream
        chunk_size: Jumlah karakter per chunk (default: 3)

    Yields:
        {"type": "token", "content": "..."}
    """
    if not text:
        return
    for i in range(0, len(text), chunk_size):
        yield {"type": "token", "content": text[i:i + chunk_size]}


# ── Legacy SSE generator (kompatibilitas) ────────────────────
def run_agent_stream(user_message: str) -> Generator[dict, None, None]:
    """Legacy SSE wrapper — delegate ke run_agent_ws."""
    yield from run_agent_ws(user_message)
