"""Windows tray launcher for the clipping server.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import uvicorn

UVICORN_HOST = "0.0.0.0"
UVICORN_PORT = 8000
SERVER_ARG = "--run-server"


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def server_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, SERVER_ARG]
    return [sys.executable, str(Path(__file__).resolve()), SERVER_ARG]


def server_log_path() -> Path:
    log_dir = application_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "tray_server.log"


def run_server() -> None:
    os.chdir(application_dir())

    from main import app as _server_app

    del _server_app
    uvicorn.run(
        "main:app",
        host=UVICORN_HOST,
        port=UVICORN_PORT,
        reload=True,
    )


def create_icon_image() -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (21, 101, 192, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 14, 56, 50), radius=10, fill=(255, 255, 255, 255))
    draw.polygon((28, 24, 28, 40, 42, 32), fill=(21, 101, 192, 255))
    return image


class TrayServer:
    def __init__(self) -> None:
        import pystray

        self.pystray = pystray
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.log_handle: Optional[Any] = None
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

        self.log_handle = server_log_path().open("ab")
        self.process = subprocess.Popen(
            server_command(),
            cwd=application_dir(),
            stdin=subprocess.DEVNULL,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )

    def stop_server(self) -> None:
        try:
            if self.process and self.process.poll() is None:
                if os.name == "nt":
                    self.process.terminate()
                else:
                    self.process.send_signal(signal.SIGTERM)

                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        finally:
            if self.log_handle:
                self.log_handle.close()
                self.log_handle = None

    def exit_app(self, icon: Any, item: Any) -> None:
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
