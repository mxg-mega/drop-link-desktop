"""History file + shared-folder handling: safe names, chunked saves, atomic writes."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from .config import settings

log = logging.getLogger("droplink.storage")

CHUNK_SIZE = 1024 * 1024
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_TOMBSTONES = 1000


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


def new_item(
    origin: str,
    item_type: str,
    item_id: Optional[str] = None,
    client_time: Optional[str] = None,
    size_bytes: Optional[int] = None,
    **fields,
) -> dict:
    # Parse client_time leniently; if invalid, use now
    created_at = None
    if client_time:
        try:
            # Try ISO 8601 formats
            created_at = datetime.fromisoformat(client_time.replace("Z", "+00:00"))
            # Clamp anything more than 5 minutes in the future
            now = datetime.now(timezone.utc)
            if created_at > now + datetime.timedelta(minutes=5):
                created_at = now
        except (ValueError, AttributeError):
            created_at = None
    
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    
    # Convert to UTC ISO with Z suffix
    created_at_str = created_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Derive HH:MM local time from created_at
    local_time = created_at.astimezone().strftime("%H:%M")
    
    item = {
        "id": item_id or str(uuid.uuid4()),
        "from": origin,
        "type": item_type,
        "time": local_time,
        "created_at": created_at_str,
        **fields,
    }
    
    # Add size_bytes for files
    if item_type == "file" and size_bytes is not None:
        item["size_bytes"] = size_bytes
    
    return item


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._migrated = False

    def _migrate_v1_to_v2(self, v1_items: list[dict]) -> dict:
        """Migrate v1 plain list to v2 format with seq numbers."""
        backup_path = self._path.with_suffix(".v1.json")
        if not backup_path.exists():
            backup_path.write_text(
                json.dumps(v1_items, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("Backed up v1 history to %s", backup_path)
        
        v2_data = {
            "version": 2,
            "seq": len(v1_items),
            "items": [],
            "tombstones": [],
            "tombstone_floor": 0,
        }
        
        for idx, item in enumerate(v1_items, start=1):
            item["seq"] = idx
            # Add size_bytes for file items if the file still exists
            if item.get("type") == "file" and "name" in item:
                file_path = settings.shared_dir / item["name"]
                if file_path.exists():
                    try:
                        item["size_bytes"] = file_path.stat().st_size
                    except OSError:
                        item["size_bytes"] = None
                else:
                    item["size_bytes"] = None
            # Set created_at to null for legacy items
            item["created_at"] = None
            v2_data["items"].append(item)
        
        return v2_data

    def _read(self) -> dict:
        if not self._path.exists():
            return {
                "version": 2,
                "seq": 0,
                "items": [],
                "tombstones": [],
                "tombstone_floor": 0,
            }
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check if it's v1 (plain list)
            if isinstance(data, list):
                log.info("Migrating history from v1 to v2 format")
                return self._migrate_v1_to_v2(data)
            
            # Validate v2 format
            if not isinstance(data, dict) or data.get("version") != 2:
                log.warning("Invalid history format, treating as empty")
                return {
                    "version": 2,
                    "seq": 0,
                    "items": [],
                    "tombstones": [],
                    "tombstone_floor": 0,
                }
            
            return data
        except (json.JSONDecodeError, OSError):
            backup = self._path.with_suffix(".corrupt.json")
            log.warning("History file unreadable, moved to %s", backup)
            try:
                os.replace(self._path, backup)
            except OSError:
                pass
            return {
                "version": 2,
                "seq": 0,
                "items": [],
                "tombstones": [],
                "tombstone_floor": 0,
            }

    def _write(self, data: dict) -> None:
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)  # atomic: a crash never leaves half a file

    def all(self) -> list[dict]:
        with self._lock:
            data = self._read()
            return data.get("items", [])

    def since(self, item_id: str) -> list[dict]:
        """Items after item_id. If it no longer exists, everything is returned."""
        items = self.all()
        for idx, item in enumerate(items):
            if item.get("id") == item_id:
                return items[idx + 1:]
        return items

    def get(self, item_id: str) -> Optional[dict]:
        """Get a specific item by id."""
        with self._lock:
            data = self._read()
            for item in data.get("items", []):
                if item.get("id") == item_id:
                    return item
            return None

    def is_deleted(self, item_id: str) -> bool:
        """Check if an item is in tombstones."""
        with self._lock:
            data = self._read()
            return any(t.get("id") == item_id for t in data.get("tombstones", []))

    def latest_seq(self) -> int:
        """Get the current sequence number."""
        with self._lock:
            data = self._read()
            return data.get("seq", 0)

    def changes_after(self, after: int) -> dict:
        """Get changes after a sequence number."""
        with self._lock:
            data = self._read()
            seq = data.get("seq", 0)
            tombstone_floor = data.get("tombstone_floor", 0)
            
            # Full resync if after is too old or too new
            if after < tombstone_floor or after > seq:
                return {
                    "latest_seq": seq,
                    "full_resync": True,
                    "items": data.get("items", []),
                    "deleted": [],
                }
            
            # Normal incremental sync
            items = [i for i in data.get("items", []) if i.get("seq", 0) > after]
            deleted = [
                t["id"]
                for t in data.get("tombstones", [])
                if t.get("seq", 0) > after
            ]
            
            return {
                "latest_seq": seq,
                "full_resync": False,
                "items": items,
                "deleted": deleted,
            }

    def add(self, item: dict) -> dict:
        with self._lock:
            data = self._read()
            data["seq"] += 1
            item["seq"] = data["seq"]
            data["items"].append(item)
            self._write(data)
        return item

    def add_if_absent(self, item: dict) -> tuple[dict, bool]:
        """Add item only if id doesn't exist. Returns (item, created)."""
        with self._lock:
            data = self._read()
            item_id = item.get("id")
            
            # Check if item already exists
            for existing in data.get("items", []):
                if existing.get("id") == item_id:
                    return existing, False
            
            # Check if it was deleted (tombstone exists)
            if any(t.get("id") == item_id for t in data.get("tombstones", [])):
                return None, False
            
            # Add new item
            data["seq"] += 1
            item["seq"] = data["seq"]
            data["items"].append(item)
            self._write(data)
            return item, True

    def remove(self, item_id: str) -> Optional[dict]:
        with self._lock:
            data = self._read()
            removed = None
            items = []
            
            for item in data.get("items", []):
                if item.get("id") == item_id:
                    removed = item
                else:
                    items.append(item)
            
            if removed is None:
                # Check if already deleted
                if any(t.get("id") == item_id for t in data.get("tombstones", [])):
                    return None  # Already in tombstones
                return None  # Never existed
            
            # Add tombstone
            data["seq"] += 1
            tombstone = {"id": item_id, "seq": data["seq"]}
            data["tombstones"].append(tombstone)
            
            # Trim tombstones if needed
            if len(data["tombstones"]) > _MAX_TOMBSTONES:
                # Keep the most recent _MAX_TOMBSTONES
                data["tombstones"] = sorted(
                    data["tombstones"], key=lambda t: t["seq"]
                )[-_MAX_TOMBSTONES:]
                data["tombstone_floor"] = data["tombstones"][0]["seq"]
            
            data["items"] = items
            self._write(data)
            return removed

    def references(self, name: str) -> bool:
        return any(i.get("name") == name for i in self.all())


history = HistoryStore(settings.history_file)
