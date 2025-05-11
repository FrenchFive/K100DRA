from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from pysrt import SubRipFile
import pysrt
import os
import subprocess
from pydub import AudioSegment

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


def subtitles(srt_path, video_input, video_output):
    # Load the video
    video = VideoFileClip(video_input)
    
    # Load the subtitles
    subtitles = pysrt.open(srt_path)
    
    # Create a list to hold text clips for subtitles
    subtitle_clips = []
    
    # Define the font size and position for the subtitles
    font_size = 50
    text_color = 'white'
    font = os.path.join(script_path, 'fonts', 'Montserrat_BLACK.ttf')
    
    # Create text clips for each subtitle
    for subtitle in subtitles:
        # Create a text clip for the subtitle
        text_clip = TextClip(subtitle.text, fontsize=font_size, color=text_color, font=font, size=(video.w - 100, None), method='caption')
        
        # Set the position and duration for the subtitle
        text_clip = text_clip.set_position(('center', 'center')).set_start(subtitle.start.ordinal / 1000).set_duration((subtitle.end.ordinal - subtitle.start.ordinal) / 1000)
        
        # Append the text clip to the list of subtitle clips
        subtitle_clips.append(text_clip)
    
    # Create a CompositeVideoClip to overlay the subtitles on the video
    final_video = CompositeVideoClip([video] + subtitle_clips)
    
    # Write the final video to a file
    final_video.write_videofile(video_output, codec='libx264', audio_codec='aac')
    
    # Close the video to free resources
    video.close()

def speedupAudio(audio_path, duration):
    # Load the audio file
    audio = AudioSegment.from_file(audio_path)
    
    # Define the speedup factor
    speedup_factor = 60 / duration
    
    # Speed up the audio
    sped_up_audio = audio.speedup(playback_speed=speedup_factor)
    
    # Export the sped up audio
    sped_up_audio.export(audio_path, format='mp3')
    
    # Return the new duration
    return 60