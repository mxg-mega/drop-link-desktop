"""Health / discovery."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import APP_NAME, settings
from ..presence import get_phone_cursor, phone_online
from ..storage import history

router = APIRouter()


@router.get("/ping")
def ping():
    return {
        "ping": "pong",
        "app": APP_NAME,
        "version": "2",
        "device_id": settings.device_id,
        "device_name": settings.device_name,
        "auth_required": settings.require_token,
        "phone_online": phone_online(),
        "latest_seq": history.latest_seq(),
        "phone_cursor_seq": get_phone_cursor(),
    }
