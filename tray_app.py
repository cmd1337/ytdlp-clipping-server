"""Windows tray launcher for the clipping server.

The packaged executable runs the FastAPI app in the same no-console process and
keeps only a small system tray icon for shutdown control.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import uvicorn

UVICORN_HOST = "0.0.0.0"
UVICORN_PORT = 8000
WINDOWS_MUTEX_NAME = "Global\\YTDLPClippingServerTrayApp"
ERROR_ALREADY_EXISTS = 183


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def acquire_single_instance_lock() -> Optional[int]:
    if os.name != "nt":
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, WINDOWS_MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return 0
    return mutex


def run_server(server_ready: threading.Event) -> uvicorn.Server:
    os.chdir(application_dir())

    from main import app

    config = uvicorn.Config(
        app,
        host=UVICORN_HOST,
        port=UVICORN_PORT,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)

    def serve() -> None:
        server_ready.set()
        server.run()

    thread = threading.Thread(target=serve, name="uvicorn-server", daemon=True)
    thread.start()
    return server


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

        self.instance_lock = acquire_single_instance_lock()
        if self.instance_lock == 0:
            raise SystemExit(0)

        self.server_ready = threading.Event()
        self.server: Optional[uvicorn.Server] = None
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
        self.server = run_server(self.server_ready)

    def stop_server(self) -> None:
        if self.server:
            self.server.should_exit = True

    def exit_app(self, icon: Any, item: Any) -> None:
        self.stop_server()
        icon.stop()

    def run(self) -> None:
        self.start_server()
        self.server_ready.wait(timeout=10)
        self.icon.run()


if __name__ == "__main__":
    TrayServer().run()