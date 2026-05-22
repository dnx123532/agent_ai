# ============================================================
# agent/tools/intel_tools.py
# Tools OSINT & intelijen: Shodan scan, intel gathering,
# dan generate laporan HTML — JARVIS V5
# ============================================================

import os
import json
import socket
from datetime import datetime
from typing import Any

from agent.config import SHODAN_API_KEY, resolve_path

# Import Shodan
try:
    import shodan
    HAS_SHODAN = True
except ImportError:
    HAS_SHODAN = False

# Import requests untuk fallback HTTP queries
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def shodan_scan(target: str) -> str:
    """
    Scan informasi host menggunakan Shodan API.
    Mendapatkan port terbuka, service, OS, dan vulnerability.

    Args:
        target: IP address atau domain yang akan di-scan

    Returns:
        String hasil scan terformat atau pesan error
    """
    if not HAS_SHODAN:
        return "Error: shodan tidak terinstall. Jalankan: pip install shodan"

    if SHODAN_API_KEY == "ISI_API_KEY_KAMU":
        return (
            "Error: Shodan API key belum diisi.\n"
            "Edit agent/config.py dan isi SHODAN_API_KEY dengan key dari https://shodan.io"
        )

    try:
        api = shodan.Shodan(SHODAN_API_KEY)

        # Resolusi domain ke IP jika perlu
        ip_address = target
        if not _is_ip_address(target):
            try:
                ip_address = socket.gethostbyname(target)
            except socket.gaierror:
                return f"Error: Tidak bisa resolve domain '{target}' ke IP address."

        # Query Shodan
        host = api.host(ip_address)

        lines = [
            f"🔍 SHODAN SCAN: {target} ({ip_address})",
            "─" * 50
        ]

        # Info dasar
        lines.append(f"\n📌 Informasi Dasar:")
        lines.append(f"  IP          : {host.get('ip_str', ip_address)}")
        lines.append(f"  Organisasi  : {host.get('org', 'N/A')}")
        lines.append(f"  ISP         : {host.get('isp', 'N/A')}")
        lines.append(f"  AS Number   : {host.get('asn', 'N/A')}")
        lines.append(f"  OS          : {host.get('os', 'Unknown')}")
        lines.append(f"  Hostname    : {', '.join(host.get('hostnames', ['N/A']))}")

        # Lokasi
        lines.append(f"\n🌍 Lokasi:")
        lines.append(f"  Negara      : {host.get('country_name', 'N/A')} ({host.get('country_code', 'N/A')})")
        lines.append(f"  Kota        : {host.get('city', 'N/A')}")
        lines.append(f"  Koordinat   : {host.get('latitude', 'N/A')}, {host.get('longitude', 'N/A')}")

        # Port dan service terbuka
        ports = host.get('ports', [])
        lines.append(f"\n🔓 Port Terbuka ({len(ports)}):")
        for item in host.get('data', [])[:10]:  # Maks 10 service
            port    = item.get('port', '?')
            proto   = item.get('transport', 'tcp')
            product = item.get('product', '')
            version = item.get('version', '')
            banner  = item.get('data', '')[:100].replace('\n', ' ')

            service_str = f"{product} {version}".strip() or "Unknown"
            lines.append(f"  {port}/{proto:<6} → {service_str}")
            if banner:
                lines.append(f"           Banner: {banner}")

        # Vulnerability
        vulns = host.get('vulns', [])
        if vulns:
            lines.append(f"\n⚠️ CVE Ditemukan ({len(vulns)}):")
            for cve in list(vulns)[:10]:
                lines.append(f"  - {cve}")

        # Tag
        tags = host.get('tags', [])
        if tags:
            lines.append(f"\n🏷️ Tags: {', '.join(tags)}")

        lines.append(f"\n⏰ Last Seen: {host.get('last_update', 'N/A')}")

        return "\n".join(lines)

    except shodan.APIError as e:
        if "No information available" in str(e):
            return f"ℹ️ Tidak ada informasi Shodan untuk {target} (IP mungkin belum pernah di-scan)."
        if "Invalid API key" in str(e):
            return "Error: Shodan API key tidak valid."
        return f"Error Shodan API: {e}"
    except Exception as e:
        return f"Error shodan_scan: {e}"


def intel_scan(target: str) -> str:
    """
    Kumpulkan informasi intelijen (OSINT) dari target.
    Menggunakan sumber publik: IP info, reverse DNS, WHOIS-like data.

    Args:
        target: IP address, domain, atau username

    Returns:
        String laporan intelijen terformat
    """
    if not HAS_REQUESTS:
        return "Error: requests tidak terinstall. Jalankan: pip install requests"

    try:
        lines = [
            f"🕵️ INTEL SCAN: {target}",
            f"⏰ Waktu scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "─" * 50
        ]

        # Resolusi nama → IP
        is_ip = _is_ip_address(target)
        resolved_ip = target

        if not is_ip:
            try:
                resolved_ip = socket.gethostbyname(target)
                lines.append(f"\n🌐 DNS Resolution: {target} → {resolved_ip}")
            except socket.gaierror:
                lines.append(f"\n⚠️ Tidak bisa resolve: {target}")

            # Reverse DNS juga
            try:
                all_ips = socket.getaddrinfo(target, None)
                unique_ips = list(set(addr[4][0] for addr in all_ips))
                if len(unique_ips) > 1:
                    lines.append(f"   Multiple IPs: {', '.join(unique_ips[:5])}")
            except Exception:
                pass

        # IP Geolocation via ip-api.com (gratis)
        try:
            resp = requests.get(
                f"http://ip-api.com/json/{resolved_ip}?fields=status,message,country,"
                f"countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,"
                f"asname,reverse,mobile,proxy,hosting,query",
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    lines.append(f"\n📍 Geolokasi IP ({resolved_ip}):")
                    lines.append(f"  Negara      : {data.get('country','N/A')} ({data.get('countryCode','N/A')})")
                    lines.append(f"  Region      : {data.get('regionName','N/A')}")
                    lines.append(f"  Kota        : {data.get('city','N/A')}")
                    lines.append(f"  Kode Pos    : {data.get('zip','N/A')}")
                    lines.append(f"  Koordinat   : {data.get('lat','N/A')}, {data.get('lon','N/A')}")
                    lines.append(f"  Timezone    : {data.get('timezone','N/A')}")
                    lines.append(f"  ISP         : {data.get('isp','N/A')}")
                    lines.append(f"  Organisasi  : {data.get('org','N/A')}")
                    lines.append(f"  AS          : {data.get('as','N/A')}")
                    lines.append(f"  Reverse DNS : {data.get('reverse','N/A')}")
                    lines.append(f"  Mobile      : {'Ya' if data.get('mobile') else 'Tidak'}")
                    lines.append(f"  Proxy/VPN   : {'Ya' if data.get('proxy') else 'Tidak'}")
                    lines.append(f"  Hosting     : {'Ya' if data.get('hosting') else 'Tidak'}")
        except Exception as e:
            lines.append(f"\n⚠️ Geolokasi gagal: {e}")

        # Cek port umum jika target adalah IP atau domain
        if is_ip or not target.startswith("@"):
            lines.append(f"\n🔌 Cek Port Umum (quick scan):")
            common_ports = {
                21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
                53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
                443: "HTTPS", 445: "SMB", 3306: "MySQL",
                3389: "RDP", 5432: "PostgreSQL", 6379: "Redis",
                8080: "HTTP-Alt", 8443: "HTTPS-Alt"
            }
            open_ports = []
            for port, service in common_ports.items():
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((resolved_ip, port))
                    if result == 0:
                        open_ports.append(f"{port}/{service}")
                    sock.close()
                except Exception:
                    pass

            if open_ports:
                lines.append(f"  Terbuka: {', '.join(open_ports)}")
            else:
                lines.append(f"  Semua port tertutup atau difilter.")

        return "\n".join(lines)

    except Exception as e:
        return f"Error intel_scan: {e}"


def generate_html_report(title: str, data: dict, filename: str) -> str:
    """
    Buat laporan HTML yang profesional dari data intelijen.

    Args:
        title:    Judul laporan
        data:     Dictionary berisi data laporan (key-value atau nested)
        filename: Nama file output .html

    Returns:
        Pesan sukses dengan path file atau pesan error
    """
    try:
        # Pastikan ekstensi .html
        if not filename.endswith(".html"):
            filename += ".html"

        output_path = resolve_path(filename)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Render data dict menjadi HTML rows
        def render_data(d: Any, depth: int = 0) -> str:
            if isinstance(d, dict):
                rows = ""
                for k, v in d.items():
                    rows += f"""
                    <tr>
                        <td class="key" style="padding-left:{depth*20+10}px">{k}</td>
                        <td class="val">{render_data(v, depth+1)}</td>
                    </tr>"""
                return f"<table class='inner'>{rows}</table>" if depth > 0 else rows
            elif isinstance(d, list):
                items = "".join(f"<li>{render_data(item, depth+1)}</li>" for item in d)
                return f"<ul>{items}</ul>"
            else:
                val = str(d)
                # Highlight link
                if val.startswith("http"):
                    return f"<a href='{val}' target='_blank'>{val}</a>"
                return val

        content_rows = render_data(data)

        html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #010409;
            color: #c9d1d9;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            padding: 20px;
        }}
        .header {{
            border: 1px solid #00ff41;
            padding: 20px;
            margin-bottom: 20px;
            background: #0d1117;
        }}
        .header h1 {{
            color: #00ff41;
            font-size: 1.8em;
            text-transform: uppercase;
            letter-spacing: 3px;
        }}
        .header .meta {{
            color: #8b949e;
            margin-top: 8px;
            font-size: 0.85em;
        }}
        .report-table {{
            width: 100%;
            border-collapse: collapse;
            background: #0d1117;
            border: 1px solid #30363d;
        }}
        .report-table tr:hover {{ background: #161b22; }}
        .report-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid #21262d;
            vertical-align: top;
        }}
        .key {{
            color: #00ff41;
            font-weight: bold;
            width: 30%;
            white-space: nowrap;
        }}
        .val {{ color: #c9d1d9; word-break: break-all; }}
        .inner {{ width: 100%; border-collapse: collapse; }}
        .inner td {{ padding: 3px 8px; border: none; }}
        ul {{ padding-left: 20px; }}
        li {{ margin: 3px 0; }}
        a {{ color: #58a6ff; }}
        .footer {{
            margin-top: 20px;
            text-align: center;
            color: #8b949e;
            font-size: 0.8em;
            border-top: 1px solid #30363d;
            padding-top: 10px;
        }}
        .badge {{
            display: inline-block;
            background: #00ff4120;
            border: 1px solid #00ff41;
            color: #00ff41;
            padding: 2px 8px;
            font-size: 0.75em;
            border-radius: 3px;
            margin-right: 6px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚡ {title}</h1>
        <div class="meta">
            <span class="badge">JARVIS V5</span>
            <span class="badge">INTEL REPORT</span>
            Dibuat: {timestamp}
        </div>
    </div>

    <table class="report-table">
        {content_rows}
    </table>

    <div class="footer">
        Generated by JARVIS V5 — {timestamp}
    </div>
</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        size = os.path.getsize(output_path)
        return f"✅ Laporan HTML dibuat: {output_path} ({size/1024:.1f} KB)"

    except Exception as e:
        return f"Error generate_html_report: {e}"


def _is_ip_address(value: str) -> bool:
    """Cek apakah string adalah valid IPv4 address."""
    try:
        parts = value.split(".")
        return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)
    except (ValueError, AttributeError):
        return False
