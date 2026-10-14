"""Optional shared-secret check. The laptop itself is always trusted."""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from .config import settings
from .network import is_local_client


def require_auth(request: Request) -> None:
    if not settings.require_token:
        return
    client = request.client.host if request.client else ""
    if is_local_client(client):
        return
    supplied = request.headers.get("x-token") or request.query_params.get("token") or ""
    if not secrets.compare_digest(supplied.encode(), settings.token.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")
