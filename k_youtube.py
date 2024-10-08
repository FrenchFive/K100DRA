import os
import logging
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.auth.exceptions import RefreshError


# Scopes required for uploading videos to YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

script_path = os.path.dirname(__file__)

def get_authenticated_service():
    creds = None
    token_path = 'token.json'
    credentials_path = 'youtube.json'

    # Load existing credentials from token.json if it exists
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(google.auth.transport.requests.Request())
            except RefreshError:
                logging.error("Failed to refresh credentials, initiating web authentication.")
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

    # Build the YouTube service
    youtube = build('youtube', 'v3', credentials=creds)
    return youtube

def upload_video(youtube, video_file, title, description, tags, category_id, privacy_status):
    """Upload the video to YouTube."""
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy_status,  # public, private, or unlisted
            "madeForKids": False,
        }
    }

    # Upload the video file
    media = MediaFileUpload(video_file, resumable=True)

    # Create and execute the upload request
    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    )

    response = request.execute()
    print(f"Video uploaded successfully: https://www.youtube.com/watch?v={response['id']}")

def publish(video_file, title, description, tags,):
    youtube = get_authenticated_service()

    category_id = "24"  # Example: 22 is for People & Blogs category
    privacy_status = "public"  # Choose from public, private, or unlisted

    upload_video(youtube, video_file, title, description, tags, category_id, privacy_status)

