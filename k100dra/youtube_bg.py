"""YouTube background sourcing — no local clutter.

Instead of keeping a folder full of huge background videos, you keep a
``backgrounds.txt`` of YouTube links. For each render we download **only the
short segment we actually need** with ``yt-dlp`` and then delete it, so the
drive stays clean.

``yt_dlp`` is imported lazily; if it isn't installed (or a link fails) the
selector falls back to the local ``videos/`` pool.
"""

from __future__ import annotations

import glob
import os
import re
from typing import Optional

from . import config


def available() -> bool:
    """True if yt-dlp can be used."""
    try:
        import yt_dlp  # noqa: F401
        return True
    except Exception:
        import shutil
        return shutil.which("yt-dlp") is not None


def short_id(url: str) -> str:
    """A short, stable id for a YouTube URL (for logs + usage memory)."""
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{6,})", url)
    return m.group(1) if m else url.rsplit("/", 1)[-1][:16]


def cache_dir() -> str:
    path = os.path.join(config.ROOT, ".cache", "bg")
    os.makedirs(path, exist_ok=True)
    return path


def video_duration(url: str) -> float:
    """Total duration of a YouTube video in seconds (0 if unknown)."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return float(info.get("duration") or 0.0)


def fetch_segment(url: str, start: float, duration: float, out_dir: Optional[str] = None,
                  keyframes: bool = False) -> str:
    """Download just ``[start, start+duration]`` of ``url`` and return its path.

    The segment is re-encoded/cropped again downstream, so by default we take the
    fast keyframe-aligned cut (``keyframes=False``).
    """
    import yt_dlp
    out_dir = out_dir or cache_dir()
    vid = short_id(url)
    out_tmpl = os.path.join(out_dir, f"bg_{vid}.%(ext)s")

    opts = {
        # Prefer a compact H.264 mp4 ≤1080p; fall back gracefully.
        "format": "bv*[ext=mp4][height<=1080]/bv*[height<=1080]/b[height<=1080]/bv*/b",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "overwrites": True,
        "download_ranges": yt_dlp.utils.download_range_func(None, [(start, start + duration)]),
        "force_keyframes_at_cuts": keyframes,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)

    if path and os.path.exists(path):
        return path
    # yt-dlp may have chosen a different extension — locate it.
    matches = [p for p in glob.glob(os.path.join(out_dir, f"bg_{vid}.*"))
               if not p.endswith(".part")]
    if matches:
        return matches[0]
    raise RuntimeError("yt-dlp produced no output file")
