"""API used by the phone app and the laptop UI."""
from __future__ import annotations

import logging
import re
import uuid as uuid_module
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..config import settings
from ..network import is_local_client
from ..security import require_auth
from ..storage import (
    history,
    human_size,
    new_item,
    resolve_shared,
    save_upload,
)

log = logging.getLogger("droplink.items")

router = APIRouter(dependencies=[Depends(require_auth)])

Origin = Literal["phone", "laptop"]
URL_RE = re.compile(r"https?://\S+")


@router.get("/history")
def get_history(since: Optional[str] = None):
    """All items, or only those after the item with id `since` (cheap polling)."""
    return {"history": history.since(since) if since else history.all()}


@router.get("/sync")
def sync(
    after: int = 0,
    request: Request = None,  # type: ignore
):
    """Incremental sync endpoint. Returns items and deletions after a sequence number."""
    # Update phone cursor if this is from a phone (not the laptop)
    client = request.client.host if request.client else ""
    device_id = request.headers.get("X-Device-Id")
    if device_id and not is_local_client(client):
        from ..presence import update_phone_cursor
        update_phone_cursor(after)
    
    return history.changes_after(after)


@router.post("/text")
def receive_text(
    text: str = Form(...),
    origin: Origin = Form("phone"),
    client_id: Optional[str] = Form(None),
    client_time: Optional[str] = Form(None),
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text is empty")
    
    # Validate client_id if provided
    item_id = None
    if client_id:
        try:
            uuid_module.UUID(client_id)
            item_id = client_id
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid client_id: must be a UUID")
    
    item = new_item(
        origin,
        "link" if URL_RE.fullmatch(text) else "text",
        item_id=item_id,
        client_time=client_time,
        text=text,
    )
    
    # Check for duplicate
    if item_id:
        existing = history.get(item_id)
        if existing:
            # Check if it was deleted
            if history.is_deleted(item_id):
                return {"status": "duplicate", "item": None, "deleted": True}
            return {"status": "duplicate", "item": existing, "deleted": False}
        
        # Use add_if_absent for atomic check-and-add
        added_item, created = history.add_if_absent(item)
        if not created:
            # Another request beat us to it
            existing = history.get(item_id)
            if existing:
                deleted = history.is_deleted(item_id)
                return {"status": "duplicate", "item": existing if not deleted else None, "deleted": deleted}
            return {"status": "duplicate", "item": None, "deleted": True}
    else:
        history.add(item)
    
    log.info("Text from %s (%d chars)", origin, len(text))
    return {"status": "ok", "item": item}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    origin: Origin = Form("phone"),
    client_id: Optional[str] = Form(None),
    client_time: Optional[str] = Form(None),
):
    # Validate client_id if provided
    item_id = None
    if client_id:
        try:
            uuid_module.UUID(client_id)
            item_id = client_id
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid client_id: must be a UUID")
    
    # Check for duplicate BEFORE saving the file
    if item_id:
        existing = history.get(item_id)
        if existing:
            # Check if it was deleted
            if history.is_deleted(item_id):
                return {"status": "duplicate", "item": None, "deleted": True}
            return {"status": "duplicate", "item": existing, "deleted": False}
    
    # Save the file
    name, size = await save_upload(file)
    
    # Create the item
    item = new_item(
        origin,
        "file",
        item_id=item_id,
        client_time=client_time,
        name=name,
        size=human_size(size),
        size_bytes=size,
    )
    
    # Add to history
    if item_id:
        added_item, created = history.add_if_absent(item)
        if not created:
            # Another request beat us to it - delete the file we just saved
            path = resolve_shared(name)
            if path is not None:
                try:
                    path.unlink()
                except OSError:
                    log.warning("Could not delete duplicate file %s", name)
            existing = history.get(item_id)
            if existing:
                deleted = history.is_deleted(item_id)
                return {"status": "duplicate", "item": existing if not deleted else None, "deleted": deleted}
            return {"status": "duplicate", "item": None, "deleted": True}
    else:
        history.add(item)
    
    log.info("File from %s: %s (%s)", origin, name, item["size"])
    return {"status": "ok", "item": item}


@router.get("/shared")
def list_shared_files():
    files = [
        {"filename": p.name, "size": human_size(p.stat().st_size)}
        for p in settings.shared_dir.iterdir()
        if p.is_file()
    ]
    return {"count": len(files), "files": files}


@router.get("/download/{filename}")
def download_file(filename: str):
    path = resolve_shared(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(path, filename=path.name)


@router.delete("/history/{item_id}")
def delete_history_item(item_id: str):
    # Check if already deleted
    if history.is_deleted(item_id):
        return {"status": "already_deleted"}
    
    removed = history.remove(item_id)
    if removed is None:
        # Check if it ever existed
        if history.get(item_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
        # It exists but remove returned None - should not happen with v2
        return {"status": "deleted"}

    name = removed.get("name")
    if removed.get("type") == "file" and name and not history.references(name):
        path = resolve_shared(name)
        if path is not None:
            try:
                path.unlink()
            except OSError as exc:  # e.g. still being downloaded on Windows
                log.warning("Could not delete %s: %s", name, exc)
    return {"status": "deleted"}
