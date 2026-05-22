# ============================================================
# agent/core/react_agent.py
# ReAct Agent Loop: THINK → ACT → OBSERVE — JARVIS V5
# Mengeksekusi tools berdasarkan respons JSON dari LLM
# ============================================================

import json
import re
from typing import Any, Generator

from agent.config import MAX_STEPS
from agent.core.llm import chat_with_retry
from agent.core.prompts import SYSTEM_PROMPT, format_observation, format_error

# ── Import semua tools ───────────────────────────────────────
from agent.tools.file_tools import (
    list_dir, create_folder, save_text, read_file, move_file
)
from agent.tools.office_tools import create_docx, create_xlsx
from agent.tools.system_tools import system_info, list_processes, run_command
from agent.tools.web_tools import web_search, open_browser
from agent.tools.intel_tools import shodan_scan, intel_scan, generate_html_report


# ── Registry tools: nama → fungsi ────────────────────────────
TOOL_REGISTRY: dict[str, Any] = {
    # File tools
    "list_dir":             list_dir,
    "create_folder":        create_folder,
    "save_text":            save_text,
    "read_file":            read_file,
    "move_file":            move_file,
    # Office tools
    "create_docx":          create_docx,
    "create_xlsx":          create_xlsx,
    # System tools
    "system_info":          system_info,
    "list_processes":       list_processes,
    "run_command":          run_command,
    # Web tools
    "web_search":           web_search,
    "open_browser":         open_browser,
    # Intel tools
    "shodan_scan":          shodan_scan,
    "intel_scan":           intel_scan,
    "generate_html_report": generate_html_report,
}


def _extract_json(text: str) -> dict:
    """
    Ekstrak JSON dari teks LLM yang mungkin mengandung markdown atau teks lain.
    Robust terhadap:
    - Teks di luar JSON
    - Code block markdown (```json ... ```)
    - Trailing koma yang tidak valid
    - Whitespace berlebih

    Args:
        text: Raw output dari LLM

    Returns:
        Dict hasil parse JSON

    Raises:
        ValueError: Jika tidak ada JSON valid yang ditemukan
    """
    # Coba parse langsung dulu
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Coba strip markdown code block
    patterns = [
        r'```json\s*([\s\S]+?)\s*```',   # ```json ... ```
        r'```\s*([\s\S]+?)\s*```',        # ``` ... ```
        r'`(\{[\s\S]+?\})`',              # `{...}`
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Cari objek JSON dengan bracket matching
    brace_count = 0
    start_idx   = None

    for i, char in enumerate(text):
        if char == '{':
            if start_idx is None:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx is not None:
                candidate = text[start_idx:i+1]
                # Bersihkan trailing koma sebelum } atau ]
                candidate = re.sub(r',(\s*[}\]])', r'\1', candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start_idx   = None
                    brace_count = 0

    raise ValueError(f"Tidak ada JSON valid dalam respons LLM:\n{text[:500]}")


def _execute_tool(action: str, action_input: dict) -> str:
    """
    Eksekusi tool berdasarkan nama dan input.

    Args:
        action:       Nama tool yang akan dijalankan
        action_input: Dict parameter untuk tool

    Returns:
        String hasil eksekusi tool
    """
    if action not in TOOL_REGISTRY:
        available = ", ".join(TOOL_REGISTRY.keys())
        return f"Error: Tool '{action}' tidak ditemukan. Tool yang tersedia: {available}"

    tool_fn = TOOL_REGISTRY[action]

    try:
        # Pastikan action_input adalah dict
        if not isinstance(action_input, dict):
            action_input = {}

        result = tool_fn(**action_input)
        return str(result)

    except TypeError as e:
        return f"Error parameter tool '{action}': {e}"
    except Exception as e:
        return f"Error saat menjalankan '{action}': {e}"


def run_agent(user_message: str) -> dict:
    """
    Jalankan ReAct agent loop untuk satu request user.
    Loop: THINK → ACT → OBSERVE (maksimal MAX_STEPS langkah)

    Args:
        user_message: Pesan atau instruksi dari user

    Returns:
        Dict dengan:
        - "answer":  Jawaban final dari agent
        - "steps":   List semua langkah (THINK/ACT/OBS)
        - "success": Boolean apakah agent berhasil
    """
    # Inisialisasi conversation
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    steps: list[dict] = []
    final_answer = ""

    for step_num in range(1, MAX_STEPS + 1):
        # ── THINK: Minta LLM berpikir ─────────────────────────
        try:
            raw_response = chat_with_retry(messages, temperature=0.3)
        except Exception as e:
            return {
                "answer":  f"Error komunikasi dengan Ollama: {e}",
                "steps":   steps,
                "success": False,
            }

        # ── Parse JSON dari respons LLM ───────────────────────
        try:
            parsed = _extract_json(raw_response)
        except ValueError:
            # LLM tidak return JSON — anggap sebagai jawaban langsung
            steps.append({
                "step":        step_num,
                "type":        "THINK",
                "thought":     "LLM tidak mengembalikan JSON terstruktur.",
                "raw":         raw_response[:300],
            })
            return {
                "answer":  raw_response,
                "steps":   steps,
                "success": True,
            }

        thought      = parsed.get("thought", "")
        action       = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        # Catat langkah THINK
        steps.append({
            "step":        step_num,
            "type":        "THINK",
            "thought":     thought,
            "action":      action,
            "action_input": action_input,
        })

        # ── Final answer? ─────────────────────────────────────
        if action == "final_answer":
            if isinstance(action_input, dict):
                final_answer = action_input.get("answer", str(action_input))
            else:
                final_answer = str(action_input)

            steps.append({
                "step":   step_num,
                "type":   "ANSWER",
                "answer": final_answer,
            })
            break

        # ── ACT: Eksekusi tool ────────────────────────────────
        if not action:
            # Tidak ada action — anggap final
            final_answer = thought or raw_response
            break

        steps.append({
            "step":        step_num,
            "type":        "ACT",
            "tool":        action,
            "input":       action_input,
        })

        # Jalankan tool
        try:
            observation = _execute_tool(action, action_input)
            obs_message = format_observation(action, observation)
        except Exception as e:
            obs_message = format_error(action, str(e))
            observation = obs_message

        # ── OBSERVE: Tambahkan hasil ke context ───────────────
        steps.append({
            "step":        step_num,
            "type":        "OBS",
            "tool":        action,
            "result":      observation[:500],  # Truncate untuk display
        })

        # Tambahkan ke conversation history
        messages.append({"role": "assistant", "content": raw_response})
        messages.append({"role": "user",      "content": obs_message})

    else:
        # Habis MAX_STEPS tanpa final_answer
        final_answer = (
            f"Saya telah mencapai batas maksimum {MAX_STEPS} langkah. "
            "Berikut ringkasan yang saya kumpulkan:\n\n"
        )
        # Kumpulkan semua observasi
        obs_list = [s["result"] for s in steps if s.get("type") == "OBS"]
        if obs_list:
            final_answer += "\n".join(obs_list[-3:])  # 3 observasi terakhir

    return {
        "answer":  final_answer,
        "steps":   steps,
        "success": True,
    }


def run_agent_stream(user_message: str) -> Generator[dict, None, None]:
    """
    Versi streaming dari run_agent() — yield setiap langkah secara real-time.
    Digunakan oleh server untuk Server-Sent Events.

    Args:
        user_message: Pesan atau instruksi dari user

    Yields:
        Dict dengan type: "step" (setiap langkah) atau "done" (jawaban final)
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    final_answer = ""

    for step_num in range(1, MAX_STEPS + 1):
        # THINK
        try:
            raw_response = chat_with_retry(messages, temperature=0.3)
        except Exception as e:
            yield {"type": "error", "message": f"Error Ollama: {e}"}
            return

        # Parse JSON
        try:
            parsed = _extract_json(raw_response)
        except ValueError:
            yield {
                "type":    "done",
                "answer":  raw_response,
                "steps":   step_num,
            }
            return

        thought      = parsed.get("thought", "")
        action       = parsed.get("action", "")
        action_input = parsed.get("action_input", {})

        # Yield THINK step
        yield {
            "type":         "THINK",
            "step":         step_num,
            "thought":      thought,
            "action":       action,
            "action_input": action_input,
        }

        # Final answer?
        if action == "final_answer":
            if isinstance(action_input, dict):
                final_answer = action_input.get("answer", str(action_input))
            else:
                final_answer = str(action_input)
            break

        if not action:
            final_answer = thought or raw_response
            break

        # Yield ACT step
        yield {
            "type":  "ACT",
            "step":  step_num,
            "tool":  action,
            "input": str(action_input)[:200],
        }

        # Eksekusi tool
        try:
            observation = _execute_tool(action, action_input)
            obs_message = format_observation(action, observation)
        except Exception as e:
            obs_message = format_error(action, str(e))
            observation = obs_message

        # Yield OBS step
        yield {
            "type":   "OBS",
            "step":   step_num,
            "tool":   action,
            "result": observation[:500],
        }

        # Update conversation
        messages.append({"role": "assistant", "content": raw_response})
        messages.append({"role": "user",      "content": obs_message})

    # Yield final done
    yield {
        "type":   "done",
        "answer": final_answer or "Proses selesai.",
    }
