import os
import json
import threading
from datetime import datetime, timedelta
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.exceptions import RefreshError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = 'token.json'
CREDENTIALS_PATH = 'youtube.json'

UPLOAD_TIMES = [10, 16]

def get_scheduled_time():
    """Return the next upload slot and update ``upload_time.json``.

    ``UPLOAD_TIMES`` defines the allowed hours (e.g. ``[10, 16]``). The script
    reads the last scheduled time from ``upload_time.json`` and chooses the next
    available hour for the current day. If all today's slots have passed, it
    rolls over to the first slot of the following day. The chosen time is
    written back to ``upload_time.json`` and returned in RFC3339 format.
    """

    json_file = "upload_time.json"
    now = datetime.now()

    last_time = None
    if os.path.exists(json_file):
        with open(json_file, "r") as file:
            try:
                last_time = datetime.fromisoformat(json.load(file).get("time"))
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

    with open(json_file, "w") as file:
        json.dump({"time": next_time.isoformat()}, file)

    return next_time.isoformat() + "Z"

def upload_chunks(request):
    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        except Exception as e:
            print(f"An error occurred: {e}")
            break
    return response

def get_authenticated_service():
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
            with open(TOKEN_PATH, 'w') as token:
                token.write(creds.to_json())

    return build('youtube', 'v3', credentials=creds)

def publish(file_path, title, description, tags):
    youtube = get_authenticated_service()
    scheduled_time = get_scheduled_time()
    body = {
        'snippet': {
            'title': (title[:96] + '...') if len(title) > 96 else title,
            'description': (description[:4996] + '...') if len(description) > 4996 else description,
            'tags': tags,
            'categoryId': '24', # Category ID for "Entertainment"
            'defaultLanguage': 'en',
            'defaultAudioLanguage': 'en',
        },
        'status': {
            'privacyStatus': 'private',  # or 'private' or 'unlisted'
            "publishAt": scheduled_time
        }
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=False
    )

    response = upload_chunks(request)
    if response:
        print("Upload Complete!")
        # Extract video ID and print the link and title
        video_id = response['id']
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"Video URL: {video_url}")
        print(f"Title: {title}")
        return response
    else:
        print("Upload failed.")
        return None