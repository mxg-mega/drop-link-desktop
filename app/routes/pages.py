"""The laptop web UI."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import TEMPLATES_DIR, settings
from ..network import get_local_ip, is_local_client, make_qr_base64

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    client = request.client.host if request.client else ""
    # The QR code carries the token, so only the laptop may see this page when auth is on.
    if settings.require_token and not is_local_client(client):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Open this page on the laptop to see the pairing QR code.",
        )

    local_ip = get_local_ip()
    full_url = f"http://{local_ip}:{settings.port}"
    pair_url = f"{full_url}/?token={settings.token}" if settings.require_token else full_url

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "local_ip": local_ip,
            "full_url": full_url,
            "qr_code": make_qr_base64(pair_url),
        },
    )
