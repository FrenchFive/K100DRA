"""Smarter background video + music selection.

The old behaviour was "pick a random file, start at a random second", which made
clips repeat and reuse the same boring segments.  This module keeps a usage
memory (``video_usage.json``) so it can:

* prefer the least-recently-used clip (and never the same one twice in a row),
* match the clip length to the narration,
* pick a *fresh segment* that does not overlap recently-used parts of that file.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import config
from .video import probe_duration

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


@dataclass
class Background:
    path: str
    start: float
    duration: float
    name: str


# --- usage memory ---------------------------------------------------------- #
def _load_usage() -> Dict:
    if os.path.exists(config.VIDEO_USAGE_FILE):
        try:
            with open(config.VIDEO_USAGE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"files": {}, "last_video": None, "last_music": None}


def _save_usage(data: Dict) -> None:
    try:
        with open(config.VIDEO_USAGE_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _list_media(folder: str, exts) -> List[str]:
    if not os.path.isdir(folder):
        return []
    return [
        f for f in os.listdir(folder)
        if f != ".gitkeep" and os.path.isfile(os.path.join(folder, f))
        and f.lower().endswith(exts)
    ]


# --- video selection ------------------------------------------------------- #
def _segment_is_fresh(start: float, duration: float, used: List[List[float]], pad: float = 5.0) -> bool:
    end = start + duration
    for u_start, u_end in used:
        if start < u_end + pad and end > u_start - pad:
            return False
    return True


def _pick_segment(total: float, duration: float, used: List[List[float]]) -> float:
    """Choose a start time, preferring segments not used before."""
    max_start = max(0.0, total - duration)
    if max_start <= 0:
        return 0.0
    for _ in range(40):
        candidate = random.uniform(0, max_start)
        if _segment_is_fresh(candidate, duration, used):
            return round(candidate, 2)
    # Everything overlaps — fall back to the gap farthest from used midpoints.
    if used:
        midpoints = [(s + e) / 2 for s, e in used]
        best, best_dist = 0.0, -1.0
        for _ in range(40):
            candidate = random.uniform(0, max_start)
            dist = min(abs(candidate + duration / 2 - m) for m in midpoints)
            if dist > best_dist:
                best, best_dist = candidate, dist
        return round(best, 2)
    return round(random.uniform(0, max_start), 2)


def select_background(duration: float) -> Background:
    folder = config.VIDEOS_DIR
    files = _list_media(folder, VIDEO_EXTS)
    if not files:
        raise FileNotFoundError(
            f"No background videos in {folder}. Drop some vertical clips in there."
        )

    usage = _load_usage()
    file_stats: Dict = usage.setdefault("files", {})

    # Score each file: long enough first, then least-used, then not-the-last-one.
    def sort_key(name: str):
        stat = file_stats.get(name, {})
        total = stat.get("duration") or probe_duration(os.path.join(folder, name))
        stat["duration"] = total
        file_stats[name] = stat
        long_enough = 0 if total >= duration + 1 else 1
        is_last = 1 if name == usage.get("last_video") and len(files) > 1 else 0
        return (long_enough, stat.get("times_used", 0), is_last, stat.get("last_used", 0))

    files.sort(key=sort_key)
    name = files[0]
    full = os.path.join(folder, name)
    total = file_stats[name].get("duration") or probe_duration(full)
    clip = min(duration, max(1.0, total))

    used_segments = file_stats[name].get("segments", [])
    start = _pick_segment(total, clip, used_segments)

    # Record usage.
    used_segments.append([start, start + clip])
    file_stats[name].update({
        "segments": used_segments[-12:],  # keep memory bounded
        "times_used": file_stats[name].get("times_used", 0) + 1,
        "last_used": time.time(),
        "duration": total,
    })
    usage["last_video"] = name
    _save_usage(usage)

    return Background(path=full, start=start, duration=clip, name=name)


# --- music selection ------------------------------------------------------- #
def select_music() -> Optional[str]:
    files = _list_media(config.MUSICS_DIR, MUSIC_EXTS)
    if not files:
        return None
    usage = _load_usage()
    last = usage.get("last_music")
    choices = [f for f in files if f != last] or files
    chosen = random.choice(choices)
    usage["last_music"] = chosen
    _save_usage(usage)
    return os.path.join(config.MUSICS_DIR, chosen)
