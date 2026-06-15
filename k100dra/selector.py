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
    temporary: bool = False   # a fetched YouTube segment we should delete after


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


def select_background(duration: float, log=None) -> Background:
    """Pick a background. Prefers YouTube links (no local clutter) per config,
    and always falls back to the local pool if needed."""
    from . import youtube_bg

    links = config.background_links()
    mode = (config.settings.bg_source or "auto").lower()
    use_youtube = (mode == "youtube") or (mode == "auto" and links and youtube_bg.available())

    if use_youtube:
        if not links:
            if log:
                log("backgrounds.txt has no links — using local videos/")
        else:
            try:
                return _select_youtube(duration, links, log)
            except Exception as exc:
                if log:
                    log(f"YouTube backgrounds failed ({exc}); falling back to local videos/")
                if mode == "youtube" and not _list_media(config.VIDEOS_DIR, VIDEO_EXTS):
                    raise

    return _select_local(duration)


def _select_youtube(duration: float, links: List[str], log=None) -> Background:
    from . import youtube_bg
    if not youtube_bg.available():
        raise RuntimeError("yt-dlp is not installed (pip install yt-dlp)")

    usage = _load_usage()
    stats: Dict = usage.setdefault("files", {})

    def key(url: str):
        s = stats.get(url, {})
        is_last = 1 if url == usage.get("last_video") and len(links) > 1 else 0
        return (s.get("times_used", 0), is_last, s.get("last_used", 0))

    # Try links in priority order so a dead/blocked link just gets skipped.
    last_exc = None
    for url in sorted(links, key=key):
        s = stats.setdefault(url, {})
        try:
            total = s.get("duration") or youtube_bg.video_duration(url)
            s["duration"] = total
            clip = min(duration, max(1.0, total)) if total else duration
            used = s.get("segments", [])
            start = _pick_segment(total or duration + 10, clip, used)
            vid = youtube_bg.short_id(url)
            if log:
                log(f"Fetching {clip:.0f}s background from YouTube ({vid}) @ {start:.0f}s")
            path = youtube_bg.fetch_segment(url, start, clip)

            used.append([start, start + clip])
            s.update({"segments": used[-12:], "times_used": s.get("times_used", 0) + 1,
                      "last_used": time.time()})
            usage["last_video"] = url
            _save_usage(usage)
            return Background(path=path, start=0.0, duration=clip, name=vid, temporary=True)
        except Exception as exc:
            last_exc = exc
            if log:
                log(f"Skipping YouTube link {youtube_bg.short_id(url)}: {exc}")
    raise RuntimeError(f"all YouTube links failed (last: {last_exc})")


def _select_local(duration: float) -> Background:
    folder = config.VIDEOS_DIR
    files = _list_media(folder, VIDEO_EXTS)
    if not files:
        raise FileNotFoundError(
            "No backgrounds available. Add YouTube links to backgrounds.txt "
            f"(and install yt-dlp), or drop clips into {folder}."
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


def cleanup(background: Optional[Background]) -> None:
    """Delete a fetched YouTube segment so the drive stays clean."""
    if not background or not background.temporary:
        return
    if config.settings.keep_bg_segments:
        return
    try:
        if os.path.exists(background.path):
            os.remove(background.path)
    except Exception:
        pass


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
