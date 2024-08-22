import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import google.auth.transport.requests
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# Scopes required for uploading videos to YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

script_path = os.path.dirname(__file__)

def get_authenticated_service():
    """Authenticate and build the YouTube API client, saving credentials for reuse."""
    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = f"{script_path}/youtube.json"
    credentials_file = f"{script_path}/token.json"  # This file will store your credentials

    creds = None
    # Check if the credentials file exists
    if os.path.exists(credentials_file):
        creds = Credentials.from_authorized_user_file(credentials_file, SCOPES)
    # If credentials are not available or invalid, initiate the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(credentials_file, 'w') as token:
            token.write(creds.to_json())

    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=creds)

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

