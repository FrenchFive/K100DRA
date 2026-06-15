"""Central configuration for the K100DRA studio.

Everything tunable lives here: paths, model names, voice settings and the
visual identity used by the new video engine.  Values are read from the
environment (a ``.env`` file is loaded automatically when ``python-dotenv`` is
installed) so the code never hard-codes secrets.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROJECTS_DIR = os.path.join(ROOT, "projects")
VIDEOS_DIR = os.path.join(ROOT, "videos")
MUSICS_DIR = os.path.join(ROOT, "musics")
FONTS_DIR = os.path.join(ROOT, "fonts")
IMGS_DIR = os.path.join(ROOT, "imgs")

# Small JSON state files kept at the repo root.
LINKS_FILE = os.path.join(ROOT, "links.txt")
BAD_LINKS_FILE = os.path.join(ROOT, "bad_links.txt")
VIDEO_USAGE_FILE = os.path.join(ROOT, "video_usage.json")
UPLOAD_TIME_FILE = os.path.join(ROOT, "upload_time.json")


def _load_dotenv() -> None:
    """Best-effort load of a ``.env`` file (optional dependency)."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(os.path.join(ROOT, ".env"))
        load_dotenv()
    except Exception:
        pass


_load_dotenv()


def _env(*names: str, default: Optional[str] = None) -> Optional[str]:
    """Return the first set environment variable among ``names``."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass
class VisualStyle:
    """Visual identity for the rendered video.

    Colours are plain ``#RRGGBB`` strings; the video engine converts them to the
    formats ffmpeg/ASS expect.
    """

    # Caption styling -------------------------------------------------------- #
    caption_font: str = "schabo.otf"          # bold condensed display font
    caption_color: str = "#FFFFFF"            # idle words
    caption_highlight: str = "#FFE000"        # the word being spoken
    caption_outline: str = "#0A0A0A"          # thick outline for readability
    caption_outline_width: int = 6
    caption_shadow: int = 3
    caption_words_per_line: int = 4           # phrase length shown at once
    caption_pop: bool = True                  # scale-pop on the active word

    # Look & feel ------------------------------------------------------------ #
    accent_color: str = "#FF2E63"             # brand accent (progress bar / UI)
    color_grade: bool = True                  # contrast / saturation / vignette
    motion_zoom: bool = True                  # slow Ken-Burns zoom on background
    progress_bar: bool = True                 # growing retention bar at bottom
    watermark: bool = True                    # small K100DRA logo
    watermark_file: str = "K100DRA_Neutral_White.png"
    watermark_opacity: float = 0.55


@dataclass
class Settings:
    # --- OpenAI (text) ------------------------------------------------------ #
    openai_key: Optional[str] = field(default_factory=lambda: _env("KEY_OPENAI", "OPENAI_API_KEY"))
    model_story: str = field(default_factory=lambda: _env("K100DRA_MODEL_STORY", default="gpt-4.1"))
    model_rate: str = field(default_factory=lambda: _env("K100DRA_MODEL_RATE", default="gpt-4o-mini"))
    model_meta: str = field(default_factory=lambda: _env("K100DRA_MODEL_META", default="gpt-4o"))
    model_srt: str = field(default_factory=lambda: _env("K100DRA_MODEL_SRT", default="gpt-4o"))
    model_transcribe: str = field(default_factory=lambda: _env("K100DRA_MODEL_TRANSCRIBE", default="whisper-1"))

    # --- ElevenLabs (voice) ------------------------------------------------- #
    elevenlabs_key: Optional[str] = field(default_factory=lambda: _env("ELEVENLABS_API_KEY", "KEY_ELEVENLABS"))
    # Default voice is "Rachel", a clear narrator voice on every ElevenLabs account.
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID", default="21m00Tcm4TlvDq8ikWAM"))
    elevenlabs_model: str = field(default_factory=lambda: _env("ELEVENLABS_MODEL", default="eleven_multilingual_v2"))
    voice_stability: float = field(default_factory=lambda: float(_env("ELEVENLABS_STABILITY", default="0.45")))
    voice_similarity: float = field(default_factory=lambda: float(_env("ELEVENLABS_SIMILARITY", default="0.8")))
    voice_style: float = field(default_factory=lambda: float(_env("ELEVENLABS_STYLE", default="0.35")))
    voice_speaker_boost: bool = field(default_factory=lambda: _env_bool("ELEVENLABS_SPEAKER_BOOST", True))
    # OpenAI voice used only as a fallback when ElevenLabs is unavailable.
    openai_tts_voice: str = field(default_factory=lambda: _env("OPENAI_TTS_VOICE", default="nova"))

    # --- Reddit ------------------------------------------------------------- #
    reddit_client_id: Optional[str] = field(default_factory=lambda: _env("REDDIT_CLIENT_ID"))
    reddit_client_secret: Optional[str] = field(default_factory=lambda: _env("REDDIT_CLIENT_SECRET"))
    reddit_user_agent: Optional[str] = field(default_factory=lambda: _env("REDDIT_USER_AGENT", default="K100DRA"))

    # --- Story / pipeline tuning ------------------------------------------- #
    target_duration: float = field(default_factory=lambda: float(_env("K100DRA_TARGET_DURATION", default="59")))
    max_script_chars: int = field(default_factory=lambda: int(_env("K100DRA_MAX_CHARS", default="1200")))
    min_story_rating: int = field(default_factory=lambda: int(_env("K100DRA_MIN_RATING", default="7")))
    max_story_attempts: int = field(default_factory=lambda: int(_env("K100DRA_MAX_ATTEMPTS", default="20")))
    music_volume_db: float = field(default_factory=lambda: float(_env("K100DRA_MUSIC_DB", default="-15")))

    # --- Publishing --------------------------------------------------------- #
    auto_upload: bool = field(default_factory=lambda: _env_bool("K100DRA_AUTO_UPLOAD", True))
    upload_privacy: str = field(default_factory=lambda: _env("K100DRA_UPLOAD_PRIVACY", default="private"))

    # --- Encoding ----------------------------------------------------------- #
    use_gpu: bool = field(default_factory=lambda: _env_bool("K100DRA_USE_GPU", True))

    visuals: VisualStyle = field(default_factory=VisualStyle)

    # ----------------------------------------------------------------------- #
    def font_path(self) -> str:
        return os.path.join(FONTS_DIR, self.visuals.caption_font)

    def watermark_path(self) -> str:
        return os.path.join(IMGS_DIR, self.visuals.watermark_file)

    def public_dict(self) -> dict:
        """A secret-free view of the settings for the UI/logs."""
        data = asdict(self)
        for secret in ("openai_key", "elevenlabs_key", "reddit_client_id", "reddit_client_secret"):
            data[secret] = bool(data.get(secret))
        return data


# A single shared instance the rest of the app imports.
settings = Settings()


# --------------------------------------------------------------------------- #
# Environment readiness
# --------------------------------------------------------------------------- #
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def readiness(s: Settings = settings) -> dict:
    """Report what the studio can and cannot do right now.

    Drives the dashboard banner and the automatic fall-back to *demo mode* when
    the real pipeline cannot run (missing keys, no ffmpeg, …).
    """
    checks = {
        "openai": {
            "ok": bool(s.openai_key),
            "label": "OpenAI (script + subtitles)",
            "hint": "Set KEY_OPENAI in your .env",
        },
        "elevenlabs": {
            "ok": bool(s.elevenlabs_key),
            "label": "ElevenLabs voice",
            "hint": "Set ELEVENLABS_API_KEY (falls back to OpenAI TTS)",
            "optional": True,
        },
        "reddit": {
            "ok": bool(s.reddit_client_id and s.reddit_client_secret),
            "label": "Reddit source",
            "hint": "Set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET",
        },
        "ffmpeg": {
            "ok": ffmpeg_available(),
            "label": "ffmpeg / ffprobe",
            "hint": "Install ffmpeg and make sure it is on PATH",
        },
        "youtube": {
            "ok": os.path.exists(os.path.join(ROOT, "youtube.json")),
            "label": "YouTube upload",
            "hint": "Place youtube.json (OAuth client) at the repo root",
            "optional": True,
        },
    }
    # Real (non-demo) runs require the non-optional pieces.
    can_run = all(c["ok"] for c in checks.values() if not c.get("optional"))
    return {"checks": checks, "can_run_real": can_run}


def ensure_dirs() -> None:
    for path in (PROJECTS_DIR, VIDEOS_DIR, MUSICS_DIR):
        os.makedirs(path, exist_ok=True)


def project_dir(project: str) -> str:
    path = os.path.join(PROJECTS_DIR, project)
    os.makedirs(path, exist_ok=True)
    return path
