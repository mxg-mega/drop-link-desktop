"""System-tray runner: lets the packaged app run without a console window."""
from __future__ import annotations

import threading
import webbrowser

import pystray
import uvicorn
from PIL import Image, ImageDraw


def _icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(61, 79, 224, 255))
    draw.ellipse((22, 22, 42, 42), fill="white")
    return img


def run_with_tray(server: uvicorn.Server, url: str, open_browser: bool = True) -> None:
    threading.Thread(target=server.run, daemon=True).start()
    if open_browser:
        threading.Timer(1.2, webbrowser.open, args=[url]).start()

    def on_open(icon, item):
        webbrowser.open(url)

    def on_quit(icon, item):
        server.should_exit = True
        icon.stop()

    icon = pystray.Icon(
        "DropLink",
        _icon_image(),
        "DropLink",
        menu=pystray.Menu(
            pystray.MenuItem("Open DropLink", on_open, default=True),
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    icon.run()  # blocks until Quit
