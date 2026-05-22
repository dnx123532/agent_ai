# ============================================================
# agent/tools/file_tools.py
# Tools untuk operasi file dan folder — JARVIS V5
# Semua path di-resolve melalui _resolve_path()
# ============================================================

import os
import shutil
from typing import Any

from agent.config import WORK_DIR, MAX_FILE_READ, resolve_path


def _resolve_path(path: str) -> str:
    """
    Shortcut ke resolve_path dari config.
    Relatif → absolut dari WORK_DIR, absolut dikembalikan apa adanya.

    Args:
        path: Path string relatif atau absolut

    Returns:
        Path absolut sebagai string
    """
    return resolve_path(path)


def list_dir(path: str = "") -> str:
    """
    Tampilkan isi folder beserta info ukuran dan tipe.

    Args:
        path: Path folder (relatif atau absolut). Default: WORK_DIR

    Returns:
        String daftar isi folder atau pesan error
    """
    try:
        target = _resolve_path(path)

        if not os.path.exists(target):
            return f"Error: Folder '{target}' tidak ditemukan."

        if not os.path.isdir(target):
            return f"Error: '{target}' bukan folder."

        items = os.listdir(target)
        if not items:
            return f"Folder '{target}' kosong."

        lines = [f"📁 Isi folder: {target}\n"]
        folders = []
        files = []

        for item in sorted(items):
            full_path = os.path.join(target, item)
            if os.path.isdir(full_path):
                folders.append(item)
            else:
                size = os.path.getsize(full_path)
                # Format ukuran file
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size/1024/1024:.1f} MB"
                files.append((item, size_str))

        # Tampilkan folder dulu
        for folder in folders:
            lines.append(f"  📂 {folder}/")

        # Lalu file
        for name, size in files:
            lines.append(f"  📄 {name} ({size})")

        lines.append(f"\nTotal: {len(folders)} folder, {len(files)} file")
        return "\n".join(lines)

    except PermissionError:
        return f"Error: Tidak ada izin untuk mengakses '{path}'."
    except Exception as e:
        return f"Error list_dir: {e}"


def create_folder(folder_path: str) -> str:
    """
    Buat folder baru, termasuk folder-folder parent yang belum ada.

    Args:
        folder_path: Path folder yang akan dibuat (relatif atau absolut)

    Returns:
        Pesan sukses atau error
    """
    try:
        target = _resolve_path(folder_path)

        if os.path.exists(target):
            return f"Folder '{target}' sudah ada."

        os.makedirs(target, exist_ok=True)
        return f"✅ Folder berhasil dibuat: {target}"

    except PermissionError:
        return f"Error: Tidak ada izin untuk membuat folder '{folder_path}'."
    except Exception as e:
        return f"Error create_folder: {e}"


def save_text(filename: str, content: str) -> str:
    """
    Simpan teks ke file. Folder parent akan dibuat otomatis jika belum ada.

    Args:
        filename: Nama/path file tujuan (relatif atau absolut)
        content:  Isi teks yang akan disimpan

    Returns:
        Pesan sukses dengan path absolut atau pesan error
    """
    try:
        target = _resolve_path(filename)

        # Buat folder parent jika belum ada
        parent_dir = os.path.dirname(target)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        size = os.path.getsize(target)
        return f"✅ File disimpan: {target} ({size} bytes)"

    except PermissionError:
        return f"Error: Tidak ada izin untuk menulis ke '{filename}'."
    except Exception as e:
        return f"Error save_text: {e}"


def read_file(filename: str) -> str:
    """
    Baca isi file teks (dibatasi MAX_FILE_READ karakter).

    Args:
        filename: Path file yang akan dibaca (relatif atau absolut)

    Returns:
        Isi file atau pesan error. Jika file terpotong, ada notifikasi.
    """
    try:
        target = _resolve_path(filename)

        if not os.path.exists(target):
            return f"Error: File '{target}' tidak ditemukan."

        if not os.path.isfile(target):
            return f"Error: '{target}' bukan file."

        # Coba berbagai encoding
        for encoding in ["utf-8", "latin-1", "cp1252"]:
            try:
                with open(target, "r", encoding=encoding) as f:
                    content = f.read(MAX_FILE_READ + 1)

                truncated = len(content) > MAX_FILE_READ
                if truncated:
                    content = content[:MAX_FILE_READ]

                result = f"📄 Isi file: {target}\n"
                result += "─" * 40 + "\n"
                result += content

                if truncated:
                    result += f"\n\n⚠️ [File dipotong — hanya {MAX_FILE_READ} karakter pertama ditampilkan]"

                return result
            except UnicodeDecodeError:
                continue

        return f"Error: File '{target}' tidak bisa dibaca (encoding tidak didukung)."

    except PermissionError:
        return f"Error: Tidak ada izin untuk membaca '{filename}'."
    except Exception as e:
        return f"Error read_file: {e}"


def move_file(src: str, dst: str) -> str:
    """
    Pindah atau rename file/folder.

    Args:
        src: Path sumber (relatif atau absolut)
        dst: Path tujuan (relatif atau absolut)

    Returns:
        Pesan sukses atau error
    """
    try:
        src_abs = _resolve_path(src)
        dst_abs = _resolve_path(dst)

        if not os.path.exists(src_abs):
            return f"Error: Sumber '{src_abs}' tidak ditemukan."

        # Buat folder parent tujuan jika belum ada
        dst_parent = os.path.dirname(dst_abs)
        if dst_parent and not os.path.exists(dst_parent):
            os.makedirs(dst_parent, exist_ok=True)

        shutil.move(src_abs, dst_abs)
        action = "dipindahkan" if os.path.dirname(src_abs) != os.path.dirname(dst_abs) else "di-rename"
        return f"✅ File berhasil {action}: {src_abs} → {dst_abs}"

    except PermissionError:
        return f"Error: Tidak ada izin untuk memindahkan '{src}'."
    except shutil.Error as e:
        return f"Error move_file: {e}"
    except Exception as e:
        return f"Error move_file: {e}"
