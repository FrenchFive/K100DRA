from moviepy import VideoFileClip, TextClip, CompositeVideoClip
from pysrt import SubRipFile
import pysrt
import os
import subprocess
from pydub import AudioSegment

script_path = os.path.dirname(__file__)

TARGET_ASPECT_RATIO = 9 / 16


def supports_nvenc():
    """Return True if ffmpeg supports the h264_nvenc encoder."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False

def length_video(video):
    """Get video length quickly using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video,
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
        )
        return float(result.stdout.strip())
    except Exception:
        videopy = VideoFileClip(video)
        return videopy.duration

def cropping(input, output, beg, duration, use_gpu=False):
    video = VideoFileClip(input)
    end_time = beg + duration

    # Subclip the video to the desired duration
    subclip = video.subclipped(beg, end_time)

    # Resize the video to 1080x1920 (9:16 aspect ratio)
    resized_video = subclip.resized(height=1280).resized(width=720)

    # Get the original video dimensions
    video_width, video_height = resized_video.size

    # Define the target aspect ratio (9:16)
    target_aspect_ratio = TARGET_ASPECT_RATIO

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
    cropped_video = resized_video.cropped(width=crop_width, height=crop_height, x_center=x_center, y_center=y_center)

    # Export the cropped and shortened video
    # Hide verbose moviepy logs but keep the progress bar
    codec = "h264_nvenc" if use_gpu and supports_nvenc() else "libx264"
    cropped_video.write_videofile(
        output,
        codec=codec,
        audio=False,
    )

def audio(video_in, audio_in, output, use_gpu=False):
# Construct the ffmpeg command
    command = [
        'ffmpeg',
        '-i', video_in,       # Input video file
        '-i', audio_in,       # Input audio file
        '-c:v', 'h264_nvenc' if use_gpu and supports_nvenc() else 'libx264',
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
        # Suppress ffmpeg output to keep the terminal clean
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except:
        print("error")


def subtitles(srt_path, video_input, video_output, use_gpu=False):
    # Load the video
    video = VideoFileClip(video_input)

    # Load the subtitles
    subtitles = pysrt.open(srt_path)

    # Create a list to hold text clips for subtitles
    subtitle_clips = []

    # Define style settings
    font_size = 35
    font_color = 'white'
    font_path = os.path.join(script_path, 'fonts', 'Montserrat_BLACK.ttf')
    print(f'-- FONT : {font_path} --')

    # Calculate generous height (e.g., 2 lines of text)
    max_lines = 2
    line_height = font_size * 1.4  # includes spacing
    box_height = int(max_lines * line_height)
    

    # Create text clips for each subtitle
    for subtitle in subtitles:
        start_time = subtitle.start.ordinal / 1000
        duration = (subtitle.end.ordinal - subtitle.start.ordinal) / 1000

        # Create the text clip (use keyword arguments only to avoid conflicts)
        text_clip = TextClip(
            text=subtitle.text,
            font_size=font_size,
            color=font_color,
            font=font_path,
            method='caption',
            stroke_color='black', # outline colour
            stroke_width=2, # thickness in pixels
            size=(video.w, box_height)  # Full width, auto height
        )

        # Set position and duration
        text_clip = text_clip.with_position(('center','center')).with_start(start_time).with_duration(duration)

        # Add to list
        subtitle_clips.append(text_clip)

    # Overlay subtitles onto the video
    final_video = CompositeVideoClip([video] + subtitle_clips)

    # Write the final output
    # Hide verbose moviepy logs but keep the progress bar
    codec = 'h264_nvenc' if use_gpu and supports_nvenc() else 'libx264'
    final_video.write_videofile(
        video_output,
        codec=codec,
        audio_codec='aac',
    )

    # Clean up
    video.close()


def speedupAudio(audio_path, duration):
    # Load the audio file
    audio = AudioSegment.from_file(audio_path)
    
    # Define the speedup factor
    speedup_factor = duration / 59
    
    # Speed up the audio
    sped_up_audio = audio.speedup(playback_speed=speedup_factor)
    
    # Export the sped up audio
    sped_up_audio.export(audio_path, format='mp3')
    
    # Return the new duration
    return len(sped_up_audio) / 1000  # Return duration in second

def add_background_music(speech_path, music_path, output_path, music_volume_dB=-15):
    speech = AudioSegment.from_file(speech_path)
    music = AudioSegment.from_file(music_path)

    # Loop or trim music to match the speech length
    if len(music) < len(speech):
        loops = int(len(speech) / len(music)) + 1
        music = music * loops
    music = music[:len(speech)]

    # Reduce music volume
    music = music - abs(music_volume_dB)

    # Combine audio
    combined = speech.overlay(music)

    # Export the result
    combined.export(output_path, format="mp3")

def upscale_to_4k_youtube(input_path, output_path, use_gpu=False):
    # Temporary file to hold the upscaled video without compression
    temp_path = "temp_upscaled.mp4"

    # Step 1: Load and upscale using MoviePy
    print("Upscaling to 3840x2160...")
    target_ar = TARGET_ASPECT_RATIO

    target_height = 2160
    target_width = int(target_height * target_ar)

    if target_width > 3840:
        target_width = 3840
        target_height = int(target_width / target_ar)

    if target_height % 2 != 0:
        target_height -= 1
    if target_width % 2 != 0:
        target_width -= 1
    
    video = VideoFileClip(input_path)
    upscaled = video.resized(height=target_height, width=target_width)
    codec = 'h264_nvenc' if use_gpu and supports_nvenc() else 'libx264'
    preset = 'fast' if codec == 'h264_nvenc' else 'ultrafast'
    upscaled.write_videofile(
        temp_path,
        codec=codec,
        preset=preset,
        audio_codec='aac',
    )
    video.close()
    upscaled.close()

    # Step 2: Re-encode with YouTube 4K recommended settings via ffmpeg
    command = [
        'ffmpeg',
        '-y',
        '-i', temp_path,
        '-c:v', 'h264_nvenc' if use_gpu and supports_nvenc() else 'libx264',
        '-b:v', '50M',               # High bitrate for 4K
        '-maxrate', '60M',
        '-bufsize', '100M',
        '-preset', 'slow',           # Better compression
        '-profile:v', 'high',
        '-level', '5.2',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '384k',
        '-movflags', '+faststart',   # Helps streaming
        output_path
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        print(f"✅ Exported YouTube 4K ready video to: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ ffmpeg error: {e}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
