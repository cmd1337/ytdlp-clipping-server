import logging
import os
from logging.handlers import RotatingFileHandler
import shlex
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ENV_PATH = ".env"
DEFAULT_LOG_FILE = "logs/app.log"
DEFAULT_VOD_FORMAT = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b"


def check_env_file() -> None:
    if os.path.exists(ENV_PATH):
        return

    with open(ENV_PATH, "w", encoding="utf-8") as env_file:
        env_file.write("AUTH_TOKEN=your_secret_secure_token_here\n")
        env_file.write("ALLOWED_DOMAINS=youtube.com,youtu.be\n")
        env_file.write("DOWNLOAD_DIR=downloads\n")
        env_file.write("SERVER_DOMAIN=\n")
        env_file.write(f"LOG_FILE={DEFAULT_LOG_FILE}\n")
        env_file.write(f"VOD_FORMAT={DEFAULT_VOD_FORMAT}\n")
        env_file.write(f"VOD_PROXY=\n")


check_env_file()
load_dotenv()


class Config:
    AUTH_TOKEN: str = os.getenv("AUTH_TOKEN", "fallback_token")
    ALLOWED_DOMAINS: List[str] = [
        domain.strip()
        for domain in os.getenv("ALLOWED_DOMAINS", "youtube.com,youtu.be").split(",")
        if domain.strip()
    ]
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "downloads")
    SERVER_DOMAIN: Optional[str] = os.getenv("SERVER_DOMAIN")
    LOG_FILE: str = os.getenv("LOG_FILE", DEFAULT_LOG_FILE)
    VOD_FORMAT: str = os.getenv("VOD_FORMAT", DEFAULT_VOD_FORMAT)
    VOD_PROXY: Optional[str] = os.getenv("VOD_PROXY") or None


if not os.path.isabs(Config.DOWNLOAD_DIR):
    Config.DOWNLOAD_DIR = os.path.abspath(Config.DOWNLOAD_DIR)
os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

if not os.path.isabs(Config.LOG_FILE):
    Config.LOG_FILE = os.path.abspath(Config.LOG_FILE)
os.makedirs(os.path.dirname(Config.LOG_FILE), exist_ok=True)


def configure_logging() -> logging.Logger:
    log_format = "%(asctime)s - [%(levelname)s] - %(module)s.py - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            RotatingFileHandler(
                Config.LOG_FILE,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        ],
        force=True,
    )

    uvicorn_loggers = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "watchfiles",
        "watchfiles.main",
    )
    for logger_name in uvicorn_loggers:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = False
        uvicorn_logger.setLevel(logging.WARNING)
        uvicorn_logger.disabled = True

    return logging.getLogger("YTDLP_Server")


logger = configure_logging()


class DownloadRequest(BaseModel):
    token: str
    link: str
    start_time: str = Field(..., examples=["01:23:45"])
    end_time: str = Field(..., examples=["01:25:00"])
    filename: str
    timescale: str = Field("normal", examples=["normal", "low", "ultralow"])
    ffmpeg_postprocessor_args: str = Field("", examples=["-vf scale=1280:-2 -c:a copy"])


def parse_ffmpeg_postprocessor_args(args: str) -> List[str]:
    if not args or not args.strip():
        return []

    try:
        parsed_args = shlex.split(args)
    except ValueError as exc:
        raise ValueError(f"Invalid ffmpeg postprocessor arguments syntax: {exc}") from exc

    return parsed_args
