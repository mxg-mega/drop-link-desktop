"""Tracks when a device other than the laptop last talked to the server."""
from __future__ import annotations

import time
from typing import Optional

_last_seen = 0.0
_phone_cursor_seq: Optional[int] = None


def touch() -> None:
    global _last_seen
    _last_seen = time.monotonic()


def phone_online(window: float = 10.0) -> bool:
    return _last_seen > 0 and (time.monotonic() - _last_seen) < window


def update_phone_cursor(after: int) -> None:
    """Update the phone's cursor to the maximum of its previous value and 'after'."""
    global _phone_cursor_seq
    if _phone_cursor_seq is None:
        _phone_cursor_seq = after
    else:
        _phone_cursor_seq = max(_phone_cursor_seq, after)


def get_phone_cursor() -> Optional[int]:
    """Get the current phone cursor sequence number."""
    return _phone_cursor_seq
