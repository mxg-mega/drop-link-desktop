"""Health / discovery."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import APP_NAME, settings
from ..presence import phone_online

router = APIRouter()


@router.get("/ping")
def ping():
    return {
        "ping": "pong",
        "app": APP_NAME,
        "phone_online": phone_online(),
        "auth_required": settings.require_token,
    }
