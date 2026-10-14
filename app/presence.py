"""Tracks when a device other than the laptop last talked to the server."""
from __future__ import annotations

import time

_last_seen = 0.0


def touch() -> None:
    global _last_seen
    _last_seen = time.monotonic()


def phone_online(window: float = 10.0) -> bool:
    return _last_seen > 0 and (time.monotonic() - _last_seen) < window
