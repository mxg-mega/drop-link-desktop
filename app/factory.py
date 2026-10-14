"""Builds the FastAPI app and wires routers together."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import presence
from .config import APP_NAME, STATIC_DIR, settings
from .network import is_local_client
from .routes import items, pages, system


def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME)

    if settings.cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def track_presence(request: Request, call_next):
        client = request.client.host if request.client else ""
        if client and not is_local_client(client):
            presence.touch()
        return await call_next(request)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(pages.router)
    app.include_router(items.router)
    app.include_router(system.router)
    return app
