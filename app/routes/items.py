"""API used by the phone app and the laptop UI."""
from __future__ import annotations

import logging
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..config import settings
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


@router.post("/text")
def receive_text(text: str = Form(...), origin: Origin = Form("phone")):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text is empty")
    item = new_item(origin, "link" if URL_RE.fullmatch(text) else "text", text=text)
    history.add(item)
    log.info("Text from %s (%d chars)", origin, len(text))
    return {"status": "ok", "item": item}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), origin: Origin = Form("phone")):
    name, size = await save_upload(file)
    item = new_item(origin, "file", name=name, size=human_size(size))
    history.add(item)
    log.info("File from %s: %s (%s)", origin, name, item["size"])
    return {"status": "uploaded", "item": item}


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
    removed = history.remove(item_id)
    if removed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    name = removed.get("name")
    if removed.get("type") == "file" and name and not history.references(name):
        path = resolve_shared(name)
        if path is not None:
            try:
                path.unlink()
            except OSError as exc:  # e.g. still being downloaded on Windows
                log.warning("Could not delete %s: %s", name, exc)
    return {"status": "deleted"}
