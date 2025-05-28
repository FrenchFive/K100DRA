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

def get_scheduled_time():
    json_file = 'upload_time.json'
    current_datetime = datetime.now()
    current_date = current_datetime.date()

    if os.path.exists(json_file):
        with open(json_file, 'r') as file:
            data = json.load(file)
            scheduled_date = datetime.strptime(data['date'], '%Y-%m-%d').date()

        if scheduled_date < current_date:
            scheduled_date = current_date
        else:
            scheduled_date += timedelta(days=1)
    else:
        scheduled_date = current_date

    # Set the time to 3 PM
    scheduled_datetime = datetime.combine(scheduled_date, datetime.min.time()) + timedelta(hours=15)

    with open(json_file, 'w') as file:
        json.dump({'date': scheduled_date.strftime('%Y-%m-%d')}, file)

    return scheduled_datetime.isoformat() + "Z"

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