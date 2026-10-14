"""DropLink entry point.

Dev:        python main.py            (console, Ctrl+C to stop)
Tray mode:  python main.py --tray     (also used automatically in the packaged build)
"""
from __future__ import annotations

import logging
import sys

import uvicorn

from app.config import APP_NAME, settings
from app.factory import create_app
from app.network import get_local_ip, pick_free_port


def _fix_noconsole() -> None:
    """A --noconsole build has no stdout/stderr, which crashes logging. Send them to a file."""
    if sys.stdout is None or sys.stderr is None:
        log_file = open(settings.data_dir / "droplink.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log_file
        sys.stderr = sys.stderr or log_file


def main() -> None:
    _fix_noconsole()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("droplink")

    settings.port = pick_free_port(settings.port)
    app = create_app()

    log.info("%s running at http://%s:%d (data in %s)", APP_NAME, get_local_ip(), settings.port, settings.data_dir)
    if settings.require_token:
        log.info("Token auth is ON. Pair the phone by scanning the QR code on the laptop page.")

    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port, log_config=None))

    use_tray = getattr(sys, "frozen", False) or "--tray" in sys.argv
    if use_tray:
        try:
            from tray import run_with_tray
        except ImportError:
            log.warning("pystray/Pillow not installed; running without a tray icon")
        else:
            run_with_tray(server, f"http://127.0.0.1:{settings.port}")
            return
    server.run()


if __name__ == "__main__":
    main()
