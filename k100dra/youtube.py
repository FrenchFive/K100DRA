"""YouTube upload + scheduling (ported from the original, made event-aware).

Google API clients are imported lazily so the studio runs without them when
``auto_upload`` is off or YouTube is not configured.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple

from . import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = os.path.join(config.ROOT, "token.json")
CREDENTIALS_PATH = os.path.join(config.ROOT, "youtube.json")
UPLOAD_TIMES = [10, 16]

ProgressCb = Optional[Callable[[float, str], None]]


def get_scheduled_time() -> str:
    now = datetime.now()
    last_time = None
    if os.path.exists(config.UPLOAD_TIME_FILE):
        try:
            with open(config.UPLOAD_TIME_FILE, "r") as fh:
                last_time = datetime.fromisoformat(json.load(fh).get("time"))
        except Exception:
            last_time = None

    base = last_time if last_time and last_time > now else now
    next_time = None
    for hour in UPLOAD_TIMES:
        candidate = base.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > base:
            next_time = candidate
            break
    if not next_time:
        next_day = base + timedelta(days=1)
        next_time = next_day.replace(hour=UPLOAD_TIMES[0], minute=0, second=0, microsecond=0)

    with open(config.UPLOAD_TIME_FILE, "w") as fh:
        json.dump({"time": next_time.isoformat()}, fh)
    return next_time.astimezone(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _authenticated_service():
    import google.auth.transport.requests
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from google.auth.exceptions import RefreshError

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(google.auth.transport.requests.Request())
            except RefreshError:
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def publish(file_path: str, title: str, description: str, tags: List[str],
            on_progress: ProgressCb = None) -> Tuple[Optional[str], str]:
    from googleapiclient.http import MediaFileUpload

    youtube = _authenticated_service()
    scheduled_time = get_scheduled_time()

    # YouTube rejects titles that are empty or contain '<' / '>'. Sanitize
    # everything defensively so a stray separator/bracket can't fail the upload.
    title = " ".join((title or "").replace("<", " ").replace(">", " ").split()).strip()
    title = (title[:100]) or "Untitled"
    description = (description or "").replace("<", "(").replace(">", ")")[:4900]
    tags = [t.replace("<", "").replace(">", "").strip() for t in (tags or [])]
    tags = [t for t in tags if t][:30]
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "24",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": config.settings.upload_privacy,
            "publishAt": scheduled_time,
        },
    }

    media = MediaFileUpload(file_path, chunksize=1024 * 1024 * 4, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media, notifySubscribers=False
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and on_progress:
            on_progress(status.progress(), f"Uploading… {int(status.progress() * 100)}%")
    if on_progress:
        on_progress(1.0, "Uploaded")

    if response:
        return f"https://www.youtube.com/watch?v={response['id']}", scheduled_time
    return None, scheduled_time
