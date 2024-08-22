from moviepy.editor import VideoFileClip, AudioFileClip
import os
import subprocess

script_path = os.path.dirname(__file__)

def len(video):
    videopy = VideoFileClip(video)
    return(videopy.duration)

def cropping(input, output, beg, duration):
    video = VideoFileClip(input)
    end_time = beg + duration

    # Get the original video dimensions (1920x1080 assumed)
    video_width, video_height = video.size

    # Define the target aspect ratio (9:16)
    target_aspect_ratio = 9 / 16

    # Calculate the target width based on the original height and target aspect ratio
    crop_width = int(video_height * target_aspect_ratio)
    crop_height = video_height

    if crop_width % 2 != 0:
        crop_width -= 1
    if crop_height % 2 != 0:
        crop_height -= 1

    # Calculate the center of the video
    x_center = video_width / 2
    y_center = video_height / 2

    # Crop the video to the new 9:16 aspect ratio, centered
    cropped_video = video.subclip(beg, end_time).crop(width=crop_width, height=crop_height, x_center=x_center, y_center=y_center)

    # Export the cropped and shortened video
    cropped_video.write_videofile(output, codec="libx264", audio=False)

def audio(video_in, audio_in, output):
# Construct the ffmpeg command
    command = [
        'ffmpeg',
        '-i', video_in,       # Input video file
        '-i', audio_in,       # Input audio file
        '-c:v', 'libx264',
        '-crf', '20',
        '-pix_fmt', 'yuv420p',
        '-b:a', '192k',
        '-c:a', 'aac',        # Set the audio codec to AAC
        '-strict', 'experimental', # Ensure the AAC codec works
        '-map', '0:v:0',      # Map the first video stream from the input video
        '-map', '1:a:0',      # Map the first audio stream from the input audio
        '-shortest',          # Ensure the output is the length of the shortest input
        output                # Output file
    ]

    # Run the command using subprocess
    try:
        subprocess.run(command, check=True)
    except:
        print("error")
