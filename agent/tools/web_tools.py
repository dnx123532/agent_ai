# ============================================================
# agent/tools/web_tools.py
# Tools untuk pencarian web dan browser — JARVIS V5
# Menggunakan Tavily API untuk web search
# ============================================================

import webbrowser
from typing import Any

from agent.config import TAVILY_API_KEY

# Import Tavily
try:
    from tavily import TavilyClient
    HAS_TAVILY = True
except ImportError:
    HAS_TAVILY = False


def web_search(query: str, max_results: int = 5) -> str:
    """
    Cari informasi di internet menggunakan Tavily Search API.

    Args:
        query:       Kata kunci atau pertanyaan yang ingin dicari
        max_results: Jumlah hasil maksimal (default: 5, max: 10)

    Returns:
        String hasil pencarian terformat atau pesan error
    """
    if not HAS_TAVILY:
        return (
            "Error: tavily-python tidak terinstall.\n"
            "Jalankan: pip install tavily-python"
        )

    if TAVILY_API_KEY == "ISI_API_KEY_KAMU":
        return (
            "Error: Tavily API key belum diisi.\n"
            "Edit agent/config.py dan isi TAVILY_API_KEY dengan key dari https://tavily.com"
        )

    try:
        # Batasi jumlah hasil
        max_results = max(1, min(10, max_results))

        client = TavilyClient(api_key=TAVILY_API_KEY)

        # Jalankan pencarian
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            include_answer=True,       # Minta jawaban ringkas
            include_raw_content=False,
        )

        lines = [f"🔍 Hasil pencarian untuk: \"{query}\"\n" + "─" * 50]

        # Tampilkan jawaban ringkas jika ada
        if response.get("answer"):
            lines.append(f"\n📌 Ringkasan:\n{response['answer']}\n")

        # Tampilkan hasil individual
        results = response.get("results", [])
        if results:
            lines.append(f"📰 Hasil ({len(results)} artikel):\n")
            for i, result in enumerate(results, 1):
                title   = result.get("title", "Tanpa Judul")
                url     = result.get("url", "")
                content = result.get("content", "")
                score   = result.get("score", 0)

                # Potong konten jika terlalu panjang
                if len(content) > 300:
                    content = content[:297] + "..."

                lines.append(f"{i}. **{title}**")
                lines.append(f"   URL   : {url}")
                if content:
                    lines.append(f"   Konten: {content}")
                lines.append(f"   Skor  : {score:.2f}")
                lines.append("")
        else:
            lines.append("Tidak ada hasil ditemukan.")

        return "\n".join(lines)

    except Exception as e:
        error_str = str(e)
        if "401" in error_str or "unauthorized" in error_str.lower():
            return "Error: Tavily API key tidak valid. Periksa kembali key kamu."
        if "429" in error_str:
            return "Error: Rate limit Tavily tercapai. Tunggu beberapa saat lalu coba lagi."
        return f"Error web_search: {e}"


def open_browser(url: str) -> str:
    """
    Buka URL di browser default sistem.

    Args:
        url: Alamat web yang akan dibuka

    Returns:
        Pesan sukses atau error
    """
    try:
        # Tambahkan https:// jika tidak ada protokol
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url

        webbrowser.open(url)
        return f"✅ Browser dibuka: {url}"

    except Exception as e:
        return f"Error open_browser: {e}"
