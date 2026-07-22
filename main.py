import string
import random
import sqlite3
import asyncio
from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager

from config import Config, DownloadRequest, logger, parse_ffmpeg_postprocessor_args
from database import init_db, get_task_db, DB_PATH
from utils import sanitize_filename
from worker import task_queue, queue_worker


def generate_task_id(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker_loop_task = asyncio.create_task(queue_worker())
    yield
    worker_loop_task.cancel()
    logger.info("Server resources cleaned up.")


app = FastAPI(title="YouTube Clip Downloader API", lifespan=lifespan)


@app.post("/download", status_code=status.HTTP_200_OK)
async def create_download_task(req: DownloadRequest):
    """
    Endpoint for downloads.
    """
    if req.token != Config.AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token"
        )

    if not any(domain in req.link for domain in Config.ALLOWED_DOMAINS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must belong to one of the allowed domains"
        )
    safe_name = sanitize_filename(req.filename)
    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is invalid or empty after purification"
        )

    try:
        parse_ffmpeg_postprocessor_args(req.ffmpeg_postprocessor_args)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    task_id = generate_task_id()
    init_desc = "In queue."

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (id, url, filename, status, description, start_time, end_time, timescale, ffmpeg_postprocessor_args)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id, req.link, safe_name, "pending", init_desc,
                req.start_time, req.end_time, req.timescale, req.ffmpeg_postprocessor_args.strip()
            )
        )
        conn.commit()

    await task_queue.put(task_id)
    logger.info(f"Task [{task_id}] accepted and enqueued.")

    return {
        "task_id": task_id,
        "queue_position": task_queue.qsize(),
        "status": "pending"
    }


@app.get("/task_status/{task_id}")
async def check_task_status(task_id: str):
    """
    Endpoint for status polling.
    """
    task = get_task_db(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task ID not found"
        )
    return {
        "status": task["status"],
        "description": task["description"]
    }