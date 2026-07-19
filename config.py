import os
import logging
from typing import Optional, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("YTDLP_Server")

ENV_PATH = ".env"
if not os.path.exists(ENV_PATH):
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("AUTH_TOKEN=fallback_token\n")
        f.write("ALLOWED_DOMAINS=youtube.com,youtu.be\n")
        f.write("DOWNLOAD_DIR=downloads\n")
        f.write("SERVER_DOMAIN=\n")

load_dotenv()

class Config:
    AUTH_TOKEN: str = os.getenv("AUTH_TOKEN", "fallback_token")
    ALLOWED_DOMAINS: List[str] = [
        d.strip() for d in os.getenv("ALLOWED_DOMAINS", "youtube.com,youtu.be").split(",") if d.strip()
    ]
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "downloads")
    SERVER_DOMAIN: Optional[str] = os.getenv("SERVER_DOMAIN")

if not os.path.isabs(Config.DOWNLOAD_DIR):
    Config.DOWNLOAD_DIR = os.path.abspath(Config.DOWNLOAD_DIR)
os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

class DownloadRequest(BaseModel):
    token: str
    link: str
    start_time: str = Field(..., examples=["01:23:45"])
    end_time: str = Field(..., examples=["01:25:00"])
    filename: str
    timescale: str = Field("normal", examples=["normal", "low", "ultralow"])