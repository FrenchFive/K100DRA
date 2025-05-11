import os
import random
import datetime
from pydub import AudioSegment
import argparse
import shutil

import k_reddit
import k_gpt4o
import k_srt
import k_movie
import k_youtube


# === Utility ===
def ensure_directories(script_path, project):
    os.makedirs(f"{script_path}/projects/{project}", exist_ok=True)
    os.makedirs(f"{script_path}/videos", exist_ok=True)
    os.makedirs(f"{script_path}/musics", exist_ok=True)


def audio_duration(path):
    duration = len(AudioSegment.from_file(path)) / 1000
    print(f"-- DURATION : {duration} --")
    return duration


# === Pipeline Steps ===
def fetch_and_generate_story(script_path, project, bypass_reddit=False, bypass_story=False, bypass_audio=False):
    subreddits = [
        "TrueOffMyChest",
        "todayilearned",
        "TIFU",
        "confessions",
        "relationships",
        "life",
        "decidingtobebetter",
        "offmychest",
        "confession",
        "FML",
    ]
    subreddit = random.choice(subreddits)
    print(f"-- SUBREDDIT :: {subreddit} --")

    if not bypass_reddit:
        title, text = k_reddit.random_post(subreddit, project)
        print(f"-- TITLE :: {title} --")
    else:
        title = "Sample Title"
        text = "Sample text for the story."
        print("-- BYPASSING REDDIT --")

    if not bypass_story:
        prompt = f"{title}\n{text}"
        story = k_gpt4o.storyfier(prompt, project)
        print("-- STORY GENERATED --")
    else:
        story = text
        print("-- BYPASSING STORY GENERATION --")

    if not bypass_audio:
        k_gpt4o.audio(story, project)
        print("-- AUDIO GENERATED --")
    else:
        orig = f"{script_path}/test/speech_test.mp3"
        dest = f"{script_path}/projects/{project}/speech.mp3"
        shutil.copy(orig, dest)
        print("-- BYPASSING AUDIO GENERATION --")

    return story, title


def prepare_audio(project, script_path):
    audio_path = f"{script_path}/projects/{project}/speech.mp3"
    duration = audio_duration(audio_path)

    if duration > 60:
        k_movie.speedupAudio(audio_path, duration)
        duration = audio_duration(audio_path)

    return audio_path, duration


def create_subtitles(project):
    k_srt.transcribe(project)
    print("-- SRT GENERATED --")


def select_background_video(duration, script_path):
    video_folder = f"{script_path}/videos"
    files = [
        f
        for f in os.listdir(video_folder)
        if os.path.isfile(os.path.join(video_folder, f)) and f != ".gitkeep"
    ]

    if not files:
        raise FileNotFoundError("No video files found in the folder.")

    video_file = random.choice(files)
    print(f"-- VIDEO SELECTED : {video_file} --")

    full_path = os.path.join(video_folder, video_file)
    total_length = k_movie.len(full_path)
    start_time = random.randint(0, int(total_length - duration))

    print(f"Start: {start_time} / Duration: {duration}")
    return full_path, start_time


def create_final_video(project, video_path, start_time, duration, script_path):
    cropped = f"{script_path}/projects/{project}/video.mp4"
    audio = f"{script_path}/projects/{project}/speech.mp3"
    video_with_audio = f"{script_path}/projects/{project}/video_audio.mp4"
    final_output = f"{script_path}/projects/{project}/video_subtitled.mp4"
    srt_file = f"{script_path}/projects/{project}/speech.srt"

    k_movie.cropping(video_path, cropped, start_time, duration)
    k_movie.audio(cropped, audio, video_with_audio)
    k_movie.subtitles(srt_file, video_with_audio, final_output)
    print("-- FINAL VIDEO GENERATED --")

def args():
    parser = argparse.ArgumentParser(description="Generate a video from a Reddit post.")
    parser.add_argument("--bp_r", action="store_true", help="Bypass Reddit fetching.")
    parser.add_argument("--bp_s", action="store_true", help="Bypass story generation.")
    parser.add_argument("--bp_a", action="store_true", help="Bypass audio generation.")
    return parser.parse_args()

def main():
    my_args = args()
    script_path = os.path.dirname(__file__)
    project = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")

    ensure_directories(script_path, project)

    story, title = fetch_and_generate_story(script_path, project, my_args.bypass_reddit, my_args.bypass_story, my_args.bypass_audio)
    audio_path, duration = prepare_audio(project, script_path)

    create_subtitles(project)

    video_path, start_time = select_background_video(duration, script_path)
    create_final_video(project, video_path, start_time, duration, script_path)

    #description, tags = k_gpt4o.ytb(project, story)

    # Uncomment this to publish:
    # k_youtube.publish(f'{script_path}/projects/{project}/video_subtitled.mp4', title, description, tags)
    # print(f'-- VIDEO PUBLISHED --')


if __name__ == "__main__":
    main()

    