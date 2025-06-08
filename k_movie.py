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
    except Exception as e:
        print(f"ffprobe failed: {e}")
        return 0.0

def cropping(input_video, output, beg, duration, use_gpu=False):
    """Crop a segment of ``input_video`` to 9:16 and save to ``output``.

    This implementation uses ffmpeg directly instead of MoviePy which is
    noticeably faster on large files.  When ``use_gpu`` is ``True`` and NVENC
    support is detected, GPU encoding is enabled.
    """

    codec = "h264_nvenc" if use_gpu and supports_nvenc() else "libx264"
    filter_str = "scale=-2:1280,crop=720:1280:(in_w-out_w)/2:(in_h-out_h)/2"

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(beg),
        "-i",
        input_video,
        "-t",
        str(duration),
        "-vf",
        filter_str,
        "-c:v",
        codec,
        "-an",
        output,
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as e:
        print(f"error running ffmpeg: {e}")

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
    except subprocess.CalledProcessError as e:
        print(f"error running ffmpeg: {e}")


def subtitles(srt_path, video_input, video_output, use_gpu=False):
    """Burn subtitles onto a video using MoviePy."""

    # Load the video
    video = VideoFileClip(video_input)

    # Load the subtitles
    subtitles = pysrt.open(srt_path)

    # Create a list to hold text clips for subtitles
    subtitle_clips = []

    # Define style settings
    # Scale font size with the height of the input video so subtitles remain
    # legible after upscaling.  8% of the height closely matches the previous
    # appearance when videos were heavily scaled.
    font_size = int(video.h * 0.08)
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
            stroke_color='black',  # outline colour
            stroke_width=10,  # thickness in pixels
            size=(video.w, box_height)
        )

        # Set position and duration
        text_clip = text_clip.with_position(('center', 'center')).with_start(start_time).with_duration(duration)

        # Add to list
        subtitle_clips.append(text_clip)

    # Overlay subtitles onto the video
    final_video = CompositeVideoClip([video] + subtitle_clips)

    # Write the final output
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
    """Upscale ``input_path`` to 4K 9:16 using ffmpeg."""

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

    scale_filter = f"scale={target_width}:{target_height}"
    codec = 'h264_nvenc' if use_gpu and supports_nvenc() else 'libx264'

    command = [
        'ffmpeg',
        '-y',
        '-i', input_path,
        '-vf', scale_filter,
        '-c:v', codec,
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
