import os
import re
from typing import Tuple

TIMESCALES = {
    "normal": 5,
    "low": 2,
    "ultralow": 1
}


def sanitize_filename(filename: str) -> str:
    invalid_chars = r'[\\/*?:"<>|]'
    return re.sub(invalid_chars, "_", filename).strip()


def parse_timerange(start_str: str, end_str: str, timescale: int) -> Tuple[int, int]:
    seconds_range = []
    for tstr in (start_str, end_str):
        t = tstr.split(":")
        total_seconds = (int(t[0]) * 60 + int(t[1])) * 60 + int(t[2])
        seconds_range.append(total_seconds)

    start_sec, end_sec = seconds_range[0], seconds_range[1]
    if start_sec >= end_sec:
        raise ValueError("Start time must be less than end time")

    start_chunk = start_sec // timescale
    end_chunk = (end_sec + timescale - 1) // timescale
    return start_chunk, end_chunk


def fragment_gen_factory(orig_gen, fragment_range: range):
    total = len(fragment_range)

    def fragment_gen(ctx):
        count = 0
        yielded = 0
        for frag in orig_gen(ctx):
            if yielded == total:
                break
            count += 1
            if count not in fragment_range:
                continue
            frag["fragment_count"] = total
            yield frag
            yielded += 1

    return fragment_gen