import yt_dlp
from yt_dlp.utils import download_range_func


def download_1080p_mp4_segment(url, start_time, end_time, output_name="output.mp4"):
    ydl_opts = {
        # Стриктный выбор: ищем видео ровно 1080p (или хуже, если 1080p нет) + лучшее аудио
        'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b',
        "proxy": "http://127.0.0.1:7890",

        # Настройки обрезки
        'download_ranges': download_range_func(None, [(start_time, end_time)]),
        'force_keyframes_at_cuts': True,

        'outtmpl': output_name,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


# Пример использования (с 1-й минуты по 1-ю минуту 30 секунд):
video_url = "https://www.youtube.com/watch?v=0spkkFeEHJ8"
download_1080p_mp4_segment(video_url, start_time=30, end_time=60)