import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload

# Scopes required for uploading videos to YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

script_path = os.path.dirname(__file__)

def get_authenticated_service():
    """Authenticate and build the YouTube API client."""
    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = f"{script_path}/youtube.json"  # Path to your OAuth 2.0 client secrets JSON file

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, SCOPES)
    credentials = flow.run_local_server(port=0)
    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)

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
            "madeForKids": True
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

