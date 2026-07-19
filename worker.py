import os
import asyncio
import sqlite3
import yt_dlp
from config import Config, logger
from database import update_task_db, DB_PATH
from utils import parse_timerange, fragment_gen_factory, TIMESCALES

task_queue: asyncio.Queue[str] = asyncio.Queue()


def run_yt_dlp_process(task_id: str, url: str, start_time_str: str, end_time_str: str, target_filename: str,
                       timescale_str: str) -> str:
    logger.info(f"[{task_id}] Extracting info for: {url}")
    final_filename = target_filename

    if any(f.startswith(final_filename) for f in os.listdir(Config.DOWNLOAD_DIR)):
        final_filename = f"{final_filename}_{task_id}"

    outtmpl_path = os.path.join(Config.DOWNLOAD_DIR, f"{final_filename}.%(ext)s")

    ydl_opts = {
        "live_from_start": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        is_live = info.get("is_live") or info.get("live_status") == "is_live"
        protocols = list(set(info.get("protocol", "").split("+")))
        is_dash_stream = "http_dash_segments_generator" in protocols

        if is_live and is_dash_stream:
            logger.info(f"[{task_id}] Processing ACTIVE YouTube Live stream.")
            timescale = TIMESCALES.get(timescale_str, TIMESCALES["normal"])
            start_chunk, end_chunk = parse_timerange(start_time_str, end_time_str, timescale)

            info["live_status"] = "was_live"
            info["is_live"] = False
            info["was_live"] = True

            chunk_range = range(start_chunk + 1, end_chunk + 1)
            for i, fmt in enumerate(info["formats"]):
                if fmt.get("fragments"):
                    info["formats"][i]["fragments"] = fragment_gen_factory(fmt["fragments"], chunk_range)

            info["id"] = final_filename
            ydl.params["outtmpl"] = {"default": outtmpl_path}
            ydl.process_info(info)

        else:
            logger.info(f"[{task_id}] Processing static video (VOD) or finished stream.")

            def to_secs(s: str) -> int:
                t = s.split(":")
                return (int(t[0]) * 60 + int(t[1])) * 60 + int(t[2])

            vod_opts = {
                "outtmpl": outtmpl_path,
                "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b",
                "proxy": "http://127.0.0.1:7890",
                "download_ranges": yt_dlp.utils.download_range_func(None, [(to_secs(start_time_str), to_secs(end_time_str))]),
                "force_keyframes_at_cuts": True,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(vod_opts) as ydl_vod:
                ydl_vod.download([url])

    actual_file = None
    for f in os.listdir(Config.DOWNLOAD_DIR):
        if f.startswith(final_filename):
            actual_file = f
            break

    if not actual_file:
        raise FileNotFoundError("yt-dlp finished but output file was not detected")

    if Config.SERVER_DOMAIN:
        base_url = Config.SERVER_DOMAIN if Config.SERVER_DOMAIN.endswith("/") else f"{Config.SERVER_DOMAIN}/"
        return f"{base_url}{actual_file}"
    else:
        return os.path.join(Config.DOWNLOAD_DIR, actual_file)


async def queue_worker() -> None:
    logger.info("Background Queue Worker initialized.")
    while True:
        task_id = await task_queue.get()
        logger.info(f"Task [{task_id}] is now active.")

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT url, filename, start_time, end_time, timescale FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

        if not row:
            task_queue.task_done()
            continue

        url = row["url"]
        filename = row["filename"]
        start_time = row["start_time"]
        end_time = row["end_time"]
        timescale_str = row["timescale"]

        update_task_db(task_id, "processing", f"Video {url} download is in progress.")

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                run_yt_dlp_process,
                task_id, url, start_time, end_time, filename, timescale_str
            )
            update_task_db(task_id, "Success", result)
        except Exception as e:
            update_task_db(task_id, "Error", f"Download failed: {str(e)}")
            logger.error(f"Task [{task_id}] failed.", exc_info=True)
        finally:
            task_queue.task_done()