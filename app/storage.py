"""History file + shared-folder handling: safe names, chunked saves, atomic writes."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from .config import settings

log = logging.getLogger("droplink.storage")

CHUNK_SIZE = 1024 * 1024
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def human_size(size_in_bytes: int) -> str:
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    if size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.2f} KB"
    if size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / 1024 ** 2:.2f} MB"
    return f"{size_in_bytes / 1024 ** 3:.2f} GB"


def sanitize_filename(name: Optional[str]) -> str:
    """Drop directory parts (either OS style) and characters Windows rejects."""
    base = Path((name or "").replace("\\", "/")).name
    base = _BAD_CHARS.sub("_", base).strip(" .")
    return (base or "upload")[:150]


def resolve_shared(name: str) -> Optional[Path]:
    """Return the file inside shared/ or None. Blocks any path that escapes the folder."""
    root = settings.shared_dir.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


async def save_upload(file: UploadFile) -> tuple[str, int]:
    """Stream to disk in chunks under a unique name. Returns (saved_name, size_in_bytes)."""
    name = sanitize_filename(file.filename)
    stem, suffix = Path(name).stem, Path(name).suffix

    n = 0
    while True:
        candidate = name if n == 0 else f"{stem} ({n}){suffix}"
        path = settings.shared_dir / candidate
        try:
            handle = open(path, "xb")  # exclusive create: two uploads can never share a name
            break
        except FileExistsError:
            n += 1

    size = 0
    try:
        with handle:
            while chunk := await file.read(CHUNK_SIZE):
                handle.write(chunk)
                size += len(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return candidate, size


def new_item(origin: str, item_type: str, **fields) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "from": origin,
        "type": item_type,
        **fields,
        "time": datetime.now().strftime("%H:%M"),
    }


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    def _read(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            backup = self._path.with_suffix(".corrupt.json")
            log.warning("History file unreadable, moved to %s", backup)
            try:
                os.replace(self._path, backup)
            except OSError:
                pass
            return []

    def _write(self, items: list[dict]) -> None:
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)  # atomic: a crash never leaves half a file

    def all(self) -> list[dict]:
        with self._lock:
            return self._read()

    def since(self, item_id: str) -> list[dict]:
        """Items after item_id. If it no longer exists, everything is returned."""
        items = self.all()
        for idx, item in enumerate(items):
            if item.get("id") == item_id:
                return items[idx + 1:]
        return items

    def add(self, item: dict) -> dict:
        with self._lock:
            items = self._read()
            items.append(item)
            self._write(items)
        return item

    def remove(self, item_id: str) -> Optional[dict]:
        with self._lock:
            items = self._read()
            removed = next((i for i in items if i.get("id") == item_id), None)
            if removed is None:
                return None
            self._write([i for i in items if i.get("id") != item_id])
            return removed

    def references(self, name: str) -> bool:
        return any(i.get("name") == name for i in self.all())


history = HistoryStore(settings.history_file)
