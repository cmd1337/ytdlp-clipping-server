"""Windows tray launcher for the clipping server.

The packaged executable starts the FastAPI app through uvicorn without opening a
console window. A tray icon is shown while the server process is running and can
be used to stop it gracefully.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pystray
import uvicorn
from PIL import Image, ImageDraw

UVICORN_HOST = "0.0.0.0"
UVICORN_PORT = 8000
SERVER_ARG = "--run-server"


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def run_server() -> None:
    os.chdir(application_dir())
    uvicorn.run(
        "main:app",
        host=UVICORN_HOST,
        port=UVICORN_PORT,
        reload=True,
    )


def create_icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (21, 101, 192, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 14, 56, 50), radius=10, fill=(255, 255, 255, 255))
    draw.polygon((28, 24, 28, 40, 42, 32), fill=(21, 101, 192, 255))
    return image


class TrayServer:
    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.icon = pystray.Icon(
            "ytdlp-clipping-server",
            create_icon_image(),
            "YTDLP Clipping Server",
            menu=pystray.Menu(
                pystray.MenuItem("Server: http://127.0.0.1:8000", None, enabled=False),
                pystray.MenuItem("Exit", self.exit_app),
            ),
        )

    def start_server(self) -> None:
        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self.process = subprocess.Popen(
            [sys.executable, SERVER_ARG],
            cwd=application_dir(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )

    def stop_server(self) -> None:
        if not self.process or self.process.poll() is not None:
            return

        if os.name == "nt":
            self.process.terminate()
        else:
            self.process.send_signal(signal.SIGTERM)

        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def exit_app(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.stop_server()
        icon.stop()

    def run(self) -> None:
        self.start_server()
        self.icon.run()


if __name__ == "__main__":
    if SERVER_ARG in sys.argv:
        run_server()
    else:
        TrayServer().run()
