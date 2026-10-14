"""Local IP discovery, port picking and the pairing QR code."""
from __future__ import annotations

import base64
import io
import socket
import time
from functools import lru_cache

import qrcode


def _host_ips() -> list[str]:
    try:
        return socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []


def get_local_ip() -> str:
    # UDP "connect" sends no packets; it only asks the OS which interface would be used.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass
    # No route (e.g. a hotspot without data): fall back to any non-loopback address.
    for ip in _host_ips():
        if not ip.startswith("127."):
            return ip
    return "127.0.0.1"


_cache = {"t": 0.0, "ips": frozenset({"127.0.0.1", "::1"})}


def local_ips() -> frozenset[str]:
    """All addresses that mean 'this laptop'. Cached briefly; hotspots change IPs."""
    now = time.monotonic()
    if now - _cache["t"] > 30:
        _cache["ips"] = frozenset({"127.0.0.1", "::1", get_local_ip(), *_host_ips()})
        _cache["t"] = now
    return _cache["ips"]


def is_local_client(host: str) -> bool:
    return host in local_ips()


def pick_free_port(start: int, tries: int = 10) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in {start}-{start + tries - 1}")


@lru_cache(maxsize=8)
def make_qr_base64(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()
