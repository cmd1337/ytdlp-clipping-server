import os
import asyncio
import sqlite3
import tempfile
import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from config import Config, logger, parse_ffmpeg_postprocessor_args
from database import update_task_db, DB_PATH
from utils import parse_timerange, fragment_gen_factory, TIMESCALES

task_queue: asyncio.Queue[str] = asyncio.Queue()


def apply_ffmpeg_postprocessing(file_path: str, args_str: str) -> str:
    ffmpeg_args = parse_ffmpeg_postprocessor_args(args_str)
    if not ffmpeg_args:
        return file_path

    file_dir = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    stem, ext = os.path.splitext(base_name)
    temp_output = None

    with tempfile.NamedTemporaryFile(
        prefix=f".{stem}.postprocess.", suffix=ext, dir=file_dir, delete=False
    ) as temp_file:
        temp_output = temp_file.name

    try:
        logger.info(f"Applying ffmpeg postprocessing to {file_path}: {args_str}")
        ffmpeg_pp = FFmpegPostProcessor()
        ffmpeg_pp.run_ffmpeg(file_path, temp_output, ffmpeg_args)
        os.replace(temp_output, file_path)
        return file_path
    except Exception:
        if temp_output and os.path.exists(temp_output):
            os.remove(temp_output)
        raise


def time_to_seconds(time_str: str) -> int:
    hours, minutes, seconds = (int(part) for part in time_str.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def apply_proxy_options(options: dict) -> dict:
    if Config.VOD_PROXY:
        options["proxy"] = Config.VOD_PROXY
    return options


def build_vod_options(outtmpl_path: str, start_time_str: str, end_time_str: str) -> dict:
    download_range = (time_to_seconds(start_time_str), time_to_seconds(end_time_str))
    vod_opts = {
        "outtmpl": outtmpl_path,
        "format": Config.VOD_FORMAT,
        "download_ranges": yt_dlp.utils.download_range_func(None, [download_range]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "no_warnings": True,
    }

    return apply_proxy_options(vod_opts)


def run_yt_dlp_process(
    task_id: str,
    url: str,
    start_time_str: str,
    end_time_str: str,
    target_filename: str,
    timescale_str: str,
    ffmpeg_postprocessor_args: str) -> str:
    logger.info(f"[{task_id}] Extracting info for: {url}")
    final_filename = target_filename

    if any(f.startswith(final_filename) for f in os.listdir(Config.DOWNLOAD_DIR)):
        final_filename = f"{final_filename}_{task_id}"

    outtmpl_path = os.path.join(Config.DOWNLOAD_DIR, f"{final_filename}.%(ext)s")

    # basic ydl_opts
    ydl_opts = apply_proxy_options({
        "live_from_start": True,
        "quiet": True,
        "no_warnings": True,
    })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        is_live = info.get("is_live") or info.get("live_status") == "is_live"
        protocols = list(set(info.get("protocol", "").split("+")))
        is_dash_stream = "http_dash_segments_generator" in protocols

        if is_live and is_dash_stream:
            logger.info(f"[{task_id}] Processing ACTIVE YouTube Live stream.")
            timescale = TIMESCALES.get(timescale_str, TIMESCALES["normal"])
            start_chunk, end_chunk = parse_timerange(start_time_str, end_time_str, timescale)

            # Tricking yt-dlp into thinking it's ended livestream
            info["live_status"] = "was_live"
            info["is_live"] = False
            info["was_live"] = True

            # magic im lazy to explain
            chunk_range = range(start_chunk + 1, end_chunk + 1)
            for i, fmt in enumerate(info["formats"]):
                if fmt.get("fragments"):
                    info["formats"][i]["fragments"] = fragment_gen_factory(fmt["fragments"], chunk_range)

            info["id"] = final_filename
            ydl.params["outtmpl"] = {"default": outtmpl_path}
            ydl.process_info(info)

        else:
            logger.info(f"[{task_id}] Processing static video (VOD) or finished stream.")

            vod_opts = build_vod_options(outtmpl_path, start_time_str, end_time_str)
            with yt_dlp.YoutubeDL(vod_opts) as ydl_vod:
                ydl_vod.download([url])

    actual_file = None
    for f in os.listdir(Config.DOWNLOAD_DIR):
        if f.startswith(final_filename):
            actual_file = f
            break

    if not actual_file:
        raise FileNotFoundError("yt-dlp finished but output file was not detected")

    actual_path = os.path.join(Config.DOWNLOAD_DIR, actual_file)
    apply_ffmpeg_postprocessing(actual_path, ffmpeg_postprocessor_args)

    logger.info(f"Clip {[final_filename]}] successfully saved to {actual_path}.")

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
            cursor.execute(
                """
                SELECT url, filename, start_time, end_time, timescale, ffmpeg_postprocessor_args
                FROM tasks WHERE id = ?
                """,
                (task_id,)
            )
            row = cursor.fetchone()

        if not row:
            task_queue.task_done()
            continue

        url = row["url"]
        filename = row["filename"]
        start_time = row["start_time"]
        end_time = row["end_time"]
        timescale_str = row["timescale"]
        ffmpeg_postprocessor_args = row["ffmpeg_postprocessor_args"] or ""

        update_task_db(task_id, "processing", f"Video {url} download is in progress.")

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                run_yt_dlp_process,
                task_id, url, start_time, end_time, filename, timescale_str, ffmpeg_postprocessor_args
            )
            update_task_db(task_id, "Success", result)
        except Exception as e:
            update_task_db(task_id, "Error", f"Download failed: {str(e)}")
            logger.error(f"Task [{task_id}] failed.", exc_info=True)
        finally:
            task_queue.task_done()