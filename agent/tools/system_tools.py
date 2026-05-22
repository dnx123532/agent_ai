# ============================================================
# agent/tools/system_tools.py
# Tools untuk informasi sistem dan eksekusi perintah — JARVIS V5
# ============================================================

import os
import subprocess
import platform
import socket
from typing import Any

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def system_info() -> str:
    """
    Ambil informasi lengkap tentang sistem yang sedang berjalan.
    Mencakup OS, CPU, RAM, disk, jaringan, dan Python.

    Returns:
        String informasi sistem terformat
    """
    try:
        lines = ["🖥️ INFORMASI SISTEM\n" + "─" * 40]

        # ── Sistem Operasi ────────────────────────────────────
        lines.append(f"\n📌 OS:")
        lines.append(f"  Sistem      : {platform.system()} {platform.release()}")
        lines.append(f"  Versi       : {platform.version()[:60]}")
        lines.append(f"  Arsitektur  : {platform.machine()}")
        lines.append(f"  Hostname    : {socket.gethostname()}")

        # ── Python ───────────────────────────────────────────
        lines.append(f"\n🐍 Python:")
        lines.append(f"  Versi       : {platform.python_version()}")
        lines.append(f"  Implementasi: {platform.python_implementation()}")

        if HAS_PSUTIL:
            # ── CPU ───────────────────────────────────────────
            cpu_count_logical  = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)
            cpu_freq = psutil.cpu_freq()
            cpu_percent = psutil.cpu_percent(interval=0.5)

            lines.append(f"\n⚙️ CPU:")
            lines.append(f"  Prosesor    : {platform.processor() or 'N/A'}")
            lines.append(f"  Core Fisik  : {cpu_count_physical}")
            lines.append(f"  Core Logis  : {cpu_count_logical}")
            if cpu_freq:
                lines.append(f"  Frekuensi   : {cpu_freq.current:.0f} MHz (max: {cpu_freq.max:.0f} MHz)")
            lines.append(f"  Penggunaan  : {cpu_percent:.1f}%")

            # ── RAM ───────────────────────────────────────────
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            lines.append(f"\n💾 RAM:")
            lines.append(f"  Total       : {mem.total / 1024**3:.2f} GB")
            lines.append(f"  Terpakai    : {mem.used / 1024**3:.2f} GB ({mem.percent:.1f}%)")
            lines.append(f"  Tersedia    : {mem.available / 1024**3:.2f} GB")
            lines.append(f"  Swap        : {swap.total / 1024**3:.2f} GB (used: {swap.percent:.1f}%)")

            # ── Disk ──────────────────────────────────────────
            lines.append(f"\n💿 Disk:")
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    lines.append(
                        f"  {partition.device} ({partition.fstype}): "
                        f"{usage.used / 1024**3:.1f} GB / {usage.total / 1024**3:.1f} GB "
                        f"({usage.percent:.1f}% terpakai)"
                    )
                except (PermissionError, OSError):
                    continue

            # ── Jaringan ──────────────────────────────────────
            lines.append(f"\n🌐 Jaringan:")
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                lines.append(f"  IP Lokal    : {local_ip}")
            except Exception:
                lines.append("  IP Lokal    : N/A")

            # Interface aktif
            net_if = psutil.net_if_addrs()
            for iface, addrs in net_if.items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        lines.append(f"  {iface:<12}: {addr.address}")

        else:
            lines.append("\n⚠️ psutil tidak terinstall — info CPU/RAM/Disk tidak tersedia")
            lines.append("   Install dengan: pip install psutil")

        return "\n".join(lines)

    except Exception as e:
        return f"Error system_info: {e}"


def list_processes(sort_by: str = "memory", limit: int = 20) -> str:
    """
    Tampilkan daftar proses yang sedang berjalan.

    Args:
        sort_by: Urutkan berdasarkan "memory" atau "cpu"
        limit:   Jumlah proses yang ditampilkan (default: 20)

    Returns:
        String daftar proses terformat atau pesan error
    """
    if not HAS_PSUTIL:
        return "Error: psutil tidak terinstall. Jalankan: pip install psutil"

    try:
        proses_list = []

        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                info = proc.info
                proses_list.append({
                    'pid':    info['pid'],
                    'name':   info['name'] or 'N/A',
                    'cpu':    info['cpu_percent'] or 0.0,
                    'memory': info['memory_percent'] or 0.0,
                    'status': info['status'] or 'N/A',
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Urutkan berdasarkan parameter
        if sort_by == "cpu":
            proses_list.sort(key=lambda x: x['cpu'], reverse=True)
            sort_label = "CPU"
        else:
            proses_list.sort(key=lambda x: x['memory'], reverse=True)
            sort_label = "Memory"

        proses_list = proses_list[:limit]

        lines = [
            f"⚙️ TOP {limit} PROSES (diurutkan berdasarkan {sort_label})\n"
            + "─" * 60,
            f"{'PID':<8} {'Nama':<30} {'CPU%':<8} {'RAM%':<8} {'Status':<12}",
            "─" * 60
        ]

        for p in proses_list:
            lines.append(
                f"{p['pid']:<8} {p['name'][:28]:<30} "
                f"{p['cpu']:<8.1f} {p['memory']:<8.2f} {p['status']:<12}"
            )

        total = len(psutil.pids())
        lines.append(f"\nTotal proses aktif: {total}")
        return "\n".join(lines)

    except Exception as e:
        return f"Error list_processes: {e}"


def run_command(command: str, timeout: int = 120) -> str:
    """
    Jalankan perintah shell/terminal.
    Mendukung semua perintah termasuk nmap, netcat, curl, dll.

    Args:
        command: Perintah yang akan dijalankan (nmap, ping, netstat, dll)
        timeout: Timeout dalam detik (default 120, naikkan untuk scan panjang)

    Returns:
        Output stdout/stderr dari perintah atau pesan error
    """
    # Hanya blokir perintah yang benar-benar merusak OS/disk
    BLOCKED_COMMANDS = [
        "format c:", "mkfs", ":(){:|:&};:",  # Fork bomb & format disk
        "rd /s /q c:\\windows", "del /f /s /q c:\\windows",
    ]

    try:
        cmd_lower = command.lower()
        for blocked in BLOCKED_COMMANDS:
            if blocked.lower() in cmd_lower:
                return f"Perintah diblokir (merusak sistem): '{blocked}'"

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )

        output_lines = []

        if result.stdout.strip():
            output_lines.append(f"[OUTPUT]\n{result.stdout.strip()}")

        if result.stderr.strip():
            output_lines.append(f"[STDERR]\n{result.stderr.strip()}")

        output_lines.append(
            f"[EXIT CODE] {result.returncode} ({'OK' if result.returncode == 0 else 'ERROR'})"
        )

        return "\n\n".join(output_lines) if output_lines else "Perintah selesai tanpa output."

    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] Perintah timeout setelah {timeout}s. Naikkan parameter timeout untuk scan panjang."
    except FileNotFoundError:
        cmd_name = command.split()[0] if command.split() else command
        return f"[NOT FOUND] Perintah '{cmd_name}' tidak ditemukan. Pastikan sudah terinstall."
    except Exception as e:
        return f"Error run_command: {e}"
