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
BACKGROUNDS_FILE = os.path.join(ROOT, "backgrounds.txt")   # YouTube background links
MUSIC_LINKS_FILE = os.path.join(ROOT, "music.txt")         # YouTube music links
VIDEO_USAGE_FILE = os.path.join(ROOT, "video_usage.json")
UPLOAD_TIME_FILE = os.path.join(ROOT, "upload_time.json")
LOG_DIR = os.path.join(ROOT, "logs")
LATEST_LOG = os.path.join(LOG_DIR, "latest.log")   # reset every run


def _load_dotenv(override: bool = False) -> None:
    """Best-effort load of a ``.env`` file (optional dependency)."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(os.path.join(ROOT, ".env"), override=override)
        load_dotenv(override=override)
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
    caption_words_per_line: int = 3           # phrase length shown at once
    caption_pop: bool = True                  # scale-pop on the active word
    caption_margin_x: int = 120               # side margins so text never spills

    # Look & feel ------------------------------------------------------------ #
    accent_color: str = "#FF2E63"             # brand accent
    color_grade: bool = True                  # contrast / saturation / vignette
    motion_zoom: bool = True                  # slow Ken-Burns zoom on background
    progress_bar: bool = False                # growing retention bar at bottom
    watermark: bool = False                   # static logo (off; handle replaces it)
    watermark_file: str = "k100dra.png"
    watermark_opacity: float = 0.55

    # Stream-clip identity --------------------------------------------------- #
    # Framed as an edited CLIP (not a livestream): a small centered avatar with a
    # Discord-style speaking glow, the caption below it, and chat at the bottom.
    stream_mode: bool = True
    handle: str = "@k100dra"                  # small attribution near the bottom
    live_badge: bool = False                  # no "LIVE" — it's a clip, not a stream
    clip_badge: bool = False
    chat_overlay: bool = True                 # live-chat reactions at the bottom
    chat_lines_visible: int = 2               # how many chat lines on screen at once
    chat_color: str = "#FFFFFF"               # chat message text
    # Her profile picture / facecam — a small centered bubble for brand recall.
    facecam: bool = True
    facecam_file: str = "k100dra.png"
    facecam_width: int = 180                  # diameter of the centered bubble
    facecam_center_y: int = 660               # vertical centre of the avatar
    facecam_round: bool = True                # circular avatar (channel-icon look)
    facecam_frame: bool = True                # thin static ring
    facecam_ring: int = 6                     # static ring thickness
    speaking_ring: bool = True                # Discord-style glow while she talks
    ring_glow: int = 22                       # glow band thickness (halo behind avatar)
    chat_font: str = "Montserrat_BLACK.ttf"   # readable font for chat/handle


@dataclass
class Settings:
    # --- Text models ------------------------------------------------------- #
    # Any model id is allowed. One starting with "claude" routes to Anthropic,
    # everything else to OpenAI. The creative writing defaults to GPT-5.5; if a
    # model id is wrong / not accessible, the run falls back to fallback_text_model.
    openai_key: Optional[str] = field(default_factory=lambda: _env("KEY_OPENAI", "OPENAI_API_KEY"))
    anthropic_key: Optional[str] = field(default_factory=lambda: _env("ANTHROPIC_API_KEY", "KEY_ANTHROPIC"))
    model_story: str = field(default_factory=lambda: _env("K100DRA_MODEL_STORY", default="gpt-5.5"))
    model_meta: str = field(default_factory=lambda: _env("K100DRA_MODEL_META", default="gpt-5.5"))
    model_rate: str = field(default_factory=lambda: _env("K100DRA_MODEL_RATE", default="gpt-4o-mini"))
    model_srt: str = field(default_factory=lambda: _env("K100DRA_MODEL_SRT", default="gpt-4o"))
    model_transcribe: str = field(default_factory=lambda: _env("K100DRA_MODEL_TRANSCRIBE", default="whisper-1"))
    fallback_text_model: str = field(default_factory=lambda: _env("K100DRA_FALLBACK_MODEL", default="gpt-4o"))

    # --- ElevenLabs (voice) ------------------------------------------------- #
    elevenlabs_key: Optional[str] = field(default_factory=lambda: _env("ELEVENLABS_API_KEY", "KEY_ELEVENLABS"))
    # Default voice is "Rachel", a clear narrator voice on every ElevenLabs account.
    elevenlabs_voice_id: str = field(default_factory=lambda: _env("ELEVENLABS_VOICE_ID", default="21m00Tcm4TlvDq8ikWAM"))
    # v3 understands inline performance tags ([excited], [whispers], ...).
    elevenlabs_model: str = field(default_factory=lambda: _env("ELEVENLABS_MODEL", default="eleven_v3"))
    voice_tags: bool = field(default_factory=lambda: _env_bool("K100DRA_VOICE_TAGS", True))
    # Lower stability + higher style = more dynamic, emphatic, "streamer"
    # delivery (lots of intonation) instead of a flat narrator read.
    voice_stability: float = field(default_factory=lambda: float(_env("ELEVENLABS_STABILITY", default="0.32")))
    voice_similarity: float = field(default_factory=lambda: float(_env("ELEVENLABS_SIMILARITY", default="0.8")))
    voice_style: float = field(default_factory=lambda: float(_env("ELEVENLABS_STYLE", default="0.55")))
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

    # --- Backgrounds -------------------------------------------------------- #
    # "auto"   → use YouTube links from backgrounds.txt if present, else videos/
    # "youtube"→ always use the links;  "local" → always use the videos/ folder.
    bg_source: str = field(default_factory=lambda: _env("K100DRA_BG_SOURCE", default="auto"))
    music_source: str = field(default_factory=lambda: _env("K100DRA_MUSIC_SOURCE", default="auto"))
    keep_bg_segments: bool = field(default_factory=lambda: _env_bool("K100DRA_KEEP_BG", False))

    # --- Encoding ----------------------------------------------------------- #
    use_gpu: bool = field(default_factory=lambda: _env_bool("K100DRA_USE_GPU", True))

    visuals: VisualStyle = field(default_factory=VisualStyle)

    # ----------------------------------------------------------------------- #
    def font_path(self) -> str:
        return os.path.join(FONTS_DIR, self.visuals.caption_font)

    def chat_font_path(self) -> str:
        return os.path.join(FONTS_DIR, self.visuals.chat_font)

    def watermark_path(self) -> str:
        return os.path.join(IMGS_DIR, self.visuals.watermark_file)

    def facecam_path(self) -> str:
        return os.path.join(IMGS_DIR, self.visuals.facecam_file)

    def public_dict(self) -> dict:
        """A secret-free view of the settings for the UI/logs."""
        data = asdict(self)
        for secret in ("openai_key", "anthropic_key", "elevenlabs_key", "reddit_client_id", "reddit_client_secret"):
            data[secret] = bool(data.get(secret))
        return data


# A single shared instance the rest of the app imports.
settings = Settings()


def reload() -> "Settings":
    """Re-read the ``.env`` and rebuild the shared settings.

    Used by the setup wizard after it writes new keys, so the running process
    picks them up without a restart.
    """
    global settings
    _load_dotenv(override=True)
    settings = Settings()
    return settings


def _read_env_pairs() -> dict:
    path = os.path.join(ROOT, ".env")
    data: dict = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def write_env_var(key: str, value: str) -> str:
    """Set a single key in the .env and reload settings (used by the UI/wizard)."""
    data = _read_env_pairs()
    data[key] = str(value)
    path = os.path.join(ROOT, ".env")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# K100DRA configuration\n")
        for k, v in data.items():
            fh.write(f"{k}={v}\n")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    os.environ[key] = str(value)
    reload()
    return value


# --------------------------------------------------------------------------- #
# Environment readiness
# --------------------------------------------------------------------------- #
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def readiness(s: Optional[Settings] = None) -> dict:
    s = s or settings
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
        "backgrounds": {
            "ok": _has_backgrounds(),
            "label": "Background footage",
            "hint": "Add YouTube links to backgrounds.txt, or clips to videos/",
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


def _has_local_videos() -> bool:
    if not os.path.isdir(VIDEOS_DIR):
        return False
    return any(f != ".gitkeep" and os.path.isfile(os.path.join(VIDEOS_DIR, f))
               for f in os.listdir(VIDEOS_DIR))


# --- Link store (background + music YouTube links, editable from the UI) ---- #
_LINK_FILES = {"background": BACKGROUNDS_FILE, "music": MUSIC_LINKS_FILE}
_LINK_HEADERS = {
    "background": "# K100DRA background links — one YouTube URL per line. Managed by the studio.\n",
    "music": "# K100DRA music links — one YouTube URL per line. Managed by the studio.\n",
}


def links_path(kind: str) -> str:
    return _LINK_FILES[kind]


def is_link(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def read_links(kind: str) -> list:
    """Non-empty, non-comment lines from the given link file."""
    path = _LINK_FILES.get(kind)
    if not path or not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def write_links(kind: str, links: list) -> list:
    """Persist a de-duplicated list of links, preserving order."""
    seen, clean = set(), []
    for link in links:
        link = link.strip()
        if link and link not in seen:
            seen.add(link)
            clean.append(link)
    with open(_LINK_FILES[kind], "w", encoding="utf-8") as fh:
        fh.write(_LINK_HEADERS[kind])
        fh.write("\n".join(clean) + ("\n" if clean else ""))
    return clean


def add_links(kind: str, urls) -> list:
    current = read_links(kind)
    for url in urls:
        url = url.strip()
        if is_link(url) and url not in current:
            current.append(url)
    return write_links(kind, current)


def remove_link(kind: str, url: str) -> list:
    return write_links(kind, [l for l in read_links(kind) if l != url])


def background_links() -> list:
    return read_links("background")


def music_links() -> list:
    return read_links("music")


def _has_backgrounds() -> bool:
    return bool(background_links()) or _has_local_videos()


def ensure_dirs() -> None:
    for path in (PROJECTS_DIR, VIDEOS_DIR, MUSICS_DIR):
        os.makedirs(path, exist_ok=True)


def project_dir(project: str) -> str:
    path = os.path.join(PROJECTS_DIR, project)
    os.makedirs(path, exist_ok=True)
    return path
