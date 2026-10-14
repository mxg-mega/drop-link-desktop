"""Settings, data folders and bundled-resource lookup."""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "DropLink"


def resource_path(rel: str) -> Path:
    """Read-only bundled files (templates, static). Works in dev and in PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


def _data_dir() -> Path:
    override = os.getenv("DROPLINK_DATA_DIR")
    path = Path(override) if override else Path(user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_token(data_dir: Path) -> str:
    """Persisted so a phone that paired once stays paired after restarts."""
    token_file = data_dir / "token.txt"
    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(9)
    token_file.write_text(token, encoding="utf-8")
    return token


class Settings:
    def __init__(self) -> None:
        self.host = os.getenv("DROPLINK_HOST", "0.0.0.0")
        self.port = int(os.getenv("DROPLINK_PORT", "8000"))
        # Off by default so the current phone app keeps working.
        # Set DROPLINK_REQUIRE_TOKEN=1 once the app sends the X-Token header.
        self.require_token = os.getenv("DROPLINK_REQUIRE_TOKEN", "0") == "1"
        # Only needed if a browser on another origin (e.g. Flutter web in dev) calls the API.
        self.cors = os.getenv("DROPLINK_CORS", "0") == "0"

        self.data_dir = _data_dir()
        self.shared_dir = self.data_dir / "shared"
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "history.json"
        self.token = _load_token(self.data_dir)


settings = Settings()

TEMPLATES_DIR = resource_path("templates")
STATIC_DIR = resource_path("static")
