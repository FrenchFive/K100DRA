"""First-run setup wizard.

Run ``python run.py`` and this walks you through everything K100DRA needs —
inputting API keys, connecting Google/YouTube — and **verifies every key is
actually valid** before you start. On later runs it just re-checks what you have
and only stops to ask when something is missing or broken.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from typing import Callable, Optional, Tuple

from . import config

ENV_PATH = os.path.join(config.ROOT, ".env")
YOUTUBE_CREDENTIALS = os.path.join(config.ROOT, "youtube.json")
YOUTUBE_TOKEN = os.path.join(config.ROOT, "token.json")
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

C_OK, C_BAD, C_DIM, C_ACC, C_RST = "\033[92m", "\033[91m", "\033[90m", "\033[95m", "\033[0m"


# --------------------------------------------------------------------------- #
# Small console helpers
# --------------------------------------------------------------------------- #
def _hr(title: str) -> None:
    print(f"\n{C_ACC}── {title} {'─' * max(0, 46 - len(title))}{C_RST}")


def _ok(msg: str) -> None:
    print(f"  {C_OK}✓{C_RST} {msg}")


def _bad(msg: str) -> None:
    print(f"  {C_BAD}✗{C_RST} {msg}")


def _info(msg: str) -> None:
    print(f"  {C_DIM}{msg}{C_RST}")


def _confirm(prompt: str, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    ans = input(f"  {prompt} {suffix} ").strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def _ask(label: str, secret: bool = True, help_url: Optional[str] = None) -> str:
    if help_url:
        print(f"  {C_DIM}↳ get it here: {help_url}{C_RST}")
    reader = getpass.getpass if secret else input
    try:
        return reader(f"  {label}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _short(exc: object) -> str:
    return str(exc).splitlines()[0][:120] if str(exc) else exc.__class__.__name__


# --------------------------------------------------------------------------- #
# .env read / write (preserves existing keys)
# --------------------------------------------------------------------------- #
def read_env() -> dict:
    data: dict = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def write_env(updates: dict) -> None:
    data = read_env()
    data.update({k: v for k, v in updates.items() if v})
    with open(ENV_PATH, "w", encoding="utf-8") as fh:
        fh.write("# K100DRA configuration (managed by the setup wizard)\n")
        for k, v in data.items():
            fh.write(f"{k}={v}\n")
    try:
        os.chmod(ENV_PATH, 0o600)
    except Exception:
        pass
    for k, v in updates.items():
        if v:
            os.environ[k] = v


def _current(env_key: str) -> Optional[str]:
    return os.environ.get(env_key) or read_env().get(env_key)


# --------------------------------------------------------------------------- #
# Validators (real API calls)
# --------------------------------------------------------------------------- #
def validate_openai(key: str) -> Tuple[bool, str]:
    try:
        import openai
        openai.OpenAI(api_key=key).models.list()
        return True, "key is valid"
    except Exception as exc:
        return False, _short(exc)


def validate_elevenlabs(key: str) -> Tuple[bool, str]:
    try:
        import requests
        r = requests.get("https://api.elevenlabs.io/v1/user",
                         headers={"xi-api-key": key}, timeout=20)
        if r.status_code == 200:
            try:
                tier = r.json().get("subscription", {}).get("tier", "")
            except Exception:
                tier = ""
            return True, f"key is valid{f' ({tier})' if tier else ''}"
        if r.status_code in (401, 403):
            return False, "key rejected (401/403)"
        return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, _short(exc)


def validate_reddit(cid: str, csec: str, agent: str) -> Tuple[bool, str]:
    try:
        import praw
        reddit = praw.Reddit(client_id=cid, client_secret=csec,
                             user_agent=agent or "K100DRA", check_for_updates=False)
        next(iter(reddit.subreddit("announcements").hot(limit=1)))
        return True, "credentials are valid"
    except Exception as exc:
        return False, _short(exc)


def validate_youtube() -> Tuple[bool, str]:
    if not os.path.exists(YOUTUBE_CREDENTIALS):
        return False, "youtube.json (OAuth client) not found"
    if not os.path.exists(YOUTUBE_TOKEN):
        return False, "not connected yet"
    try:
        from google.oauth2.credentials import Credentials
        import google.auth.transport.requests as greq
        creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN, YOUTUBE_SCOPES)
        if creds and creds.valid:
            return True, "connected"
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(greq.Request())
            with open(YOUTUBE_TOKEN, "w") as fh:
                fh.write(creds.to_json())
            return True, "connected (token refreshed)"
        return False, "saved token is invalid"
    except Exception as exc:
        return False, _short(exc)


def connect_youtube() -> Tuple[bool, str]:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        _info("A browser window will open — sign in and approve YouTube upload access.")
        flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CREDENTIALS, YOUTUBE_SCOPES)
        creds = flow.run_local_server(port=0)
        with open(YOUTUBE_TOKEN, "w") as fh:
            fh.write(creds.to_json())
        return True, "connected"
    except Exception as exc:
        return False, _short(exc)


# --------------------------------------------------------------------------- #
# Dependencies + ffmpeg
# --------------------------------------------------------------------------- #
def ensure_dependencies(interactive: bool) -> bool:
    needed = ["openai", "praw", "pydub", "fastapi", "uvicorn", "dotenv", "requests"]
    missing = [m for m in needed if not _importable(m)]
    if not missing:
        _ok("Python packages installed")
        return True
    _bad(f"missing packages: {', '.join(missing)}")
    if interactive and _confirm("Install them now from requirements.txt?", True):
        subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                        os.path.join(config.ROOT, "requirements.txt")])
        still = [m for m in missing if not _importable(m)]
        if still:
            _bad(f"still missing: {', '.join(still)}")
            return False
        _ok("packages installed")
        return True
    _info("Run:  pip install -r requirements.txt")
    return False


def _importable(mod: str) -> bool:
    """Is a module installed? Checked WITHOUT importing it (find_spec is fast;
    actually importing openai/praw/uvicorn here is slow enough to look frozen)."""
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def check_ffmpeg() -> bool:
    if config.ffmpeg_available():
        _ok("ffmpeg + ffprobe found")
        return True
    _bad("ffmpeg / ffprobe not found on PATH")
    _info("macOS:  brew install ffmpeg")
    _info("Ubuntu: sudo apt install ffmpeg")
    _info("Windows: https://ffmpeg.org/download.html (add to PATH)")
    return False


# --------------------------------------------------------------------------- #
# Per-service steps
# --------------------------------------------------------------------------- #
def _configure_simple(title: str, env_key: str, validator: Callable[[str], Tuple[bool, str]],
                      required: bool, help_url: str, verify: bool, interactive: bool,
                      force: bool) -> bool:
    _hr(title)
    cur = _current(env_key)
    if cur and not force:
        if verify:
            _info("verifying…")
        ok, msg = validator(cur) if verify else (True, "present (not verified)")
        (_ok if ok else _bad)(msg)
        if ok:
            return True
        if not interactive:
            return False
        _info("The saved key isn't working — let's replace it.")
    elif not cur and not required and not force:
        if not interactive:
            _info(f"{title} not set (optional) — skipping")
            return False
        if not _confirm(f"Set up {title} now? (optional)", default=False):
            _info("skipped")
            return False

    if not interactive:
        _bad(f"{title} not configured")
        return False

    while True:
        val = _ask(f"Paste your {title} key", help_url=help_url)
        if not val:
            if required and not _confirm("This one is required. Skip anyway?", False):
                continue
            _info("skipped")
            return False
        ok, msg = validator(val) if verify else (True, "saved (not verified)")
        if ok:
            write_env({env_key: val})
            _ok(msg)
            return True
        _bad(msg)
        if not _confirm("Try a different key?", True):
            return False


def _configure_reddit(verify: bool, interactive: bool, force: bool) -> bool:
    _hr("Reddit")
    cid, csec = _current("REDDIT_CLIENT_ID"), _current("REDDIT_CLIENT_SECRET")
    agent = _current("REDDIT_USER_AGENT") or "K100DRA"
    if cid and csec and not force:
        if verify:
            _info("verifying…")
        ok, msg = validate_reddit(cid, csec, agent) if verify else (True, "present (not verified)")
        (_ok if ok else _bad)(msg)
        if ok:
            return True
        if not interactive:
            return False
        _info("Reddit credentials aren't working — let's re-enter them.")
    if not interactive:
        _bad("Reddit not configured")
        return False

    _info("Create a 'script' app at https://www.reddit.com/prefs/apps")
    while True:
        cid = _ask("Reddit client ID", secret=False) or cid
        csec = _ask("Reddit client secret") or csec
        agent = (_ask("User agent", secret=False) or agent or "K100DRA")
        if not (cid and csec):
            if not _confirm("Both ID and secret are required. Skip Reddit?", False):
                continue
            _info("skipped")
            return False
        ok, msg = validate_reddit(cid, csec, agent) if verify else (True, "saved (not verified)")
        if ok:
            write_env({"REDDIT_CLIENT_ID": cid, "REDDIT_CLIENT_SECRET": csec,
                       "REDDIT_USER_AGENT": agent})
            _ok(msg)
            return True
        _bad(msg)
        if not _confirm("Try again?", True):
            return False


def _configure_youtube(interactive: bool, force: bool) -> bool:
    _hr("YouTube upload (optional)")
    ok, msg = validate_youtube()
    if ok and not force:
        _ok(msg)
        return True

    if not os.path.exists(YOUTUBE_CREDENTIALS):
        _bad("youtube.json not found")
        _info("In Google Cloud Console: create an OAuth client (Desktop app) for the")
        _info("YouTube Data API v3, download it, and save it as 'youtube.json' here.")
        if interactive and sys.stdin.isatty():
            input("  Press Enter once youtube.json is in place (or Ctrl-C to skip)… ")
        if not os.path.exists(YOUTUBE_CREDENTIALS):
            _info("skipped — auto-upload will stay off")
            return False

    if not interactive:
        _info("youtube.json present but not connected — run setup interactively to connect")
        return False
    if _confirm("Connect your YouTube account now?", True):
        ok, msg = connect_youtube()
        (_ok if ok else _bad)(msg)
        return ok
    _info("skipped")
    return False


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def ensure_ready(verify: bool = True, force: bool = False,
                 interactive: Optional[bool] = None) -> dict:
    """Walk through setup, verifying everything. Returns final readiness."""
    if interactive is None:
        interactive = sys.stdin.isatty()

    _hr("Dependencies")
    ensure_dependencies(interactive)
    check_ffmpeg()
    config.reload()

    _configure_simple("OpenAI", "KEY_OPENAI", validate_openai, required=True,
                      help_url="https://platform.openai.com/api-keys",
                      verify=verify, interactive=interactive, force=force)
    _configure_simple("ElevenLabs", "ELEVENLABS_API_KEY", validate_elevenlabs,
                      required=False, help_url="https://elevenlabs.io/app/settings/api-keys",
                      verify=verify, interactive=interactive, force=force)
    _configure_reddit(verify=verify, interactive=interactive, force=force)
    _configure_youtube(interactive=interactive, force=force)

    config.reload()
    return summary()


def summary() -> dict:
    rd = config.readiness()
    _hr("Setup summary")
    for c in rd["checks"].values():
        tag = "" if not c.get("optional") else "  (optional)"
        (_ok if c["ok"] else _bad)(f"{c['label']}{tag}")
    if rd["can_run_real"]:
        _ok("Everything required is ready — let's go! 🎬")
    else:
        _bad("Some required setup is still missing (you can still use Demo mode).")
    return rd
