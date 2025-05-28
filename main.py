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
    return duration


# === Pipeline Steps ===
def fetch_and_generate_story(script_path, project, bypass_reddit=False, bypass_story=False, bypass_audio=False):
    subreddits = [
        "TrueOffMyChest",
        "todayilearned",
        "TIFU",
        "confessions",
        "FanTheories",
        "TalesFromRetail",
        "decidingtobebetter",
        "offmychest",
        "confession",
        "FML",
        "AmItheAsshole",
        "BestofRedditorUpdates",
        "MadeMeSmile",
        "funfacts",
        "UnpopularOpinion"
    ]
    
    attempts = 0
    max_attempts = 20
    rating = 0
    ideal_rating = 7

    # Check if links file exists, if not create it
    links_path = f"{script_path}/links.txt"
    if not os.path.exists(f"{script_path}/links.txt"):
        with open(links_path, "w", encoding="utf-8") as file:
            file.write("")

    list_of_ids = []
    with open(links_path, "r", encoding="utf-8") as file:
        for line in file:
            list_of_ids.append(line.strip())

    if not bypass_reddit:
        while rating < ideal_rating and attempts < max_attempts:
            subreddit = random.choice(subreddits)
            title, text, link, id = k_reddit.random_post(subreddit, project) 
            
            if id not in list_of_ids:
                rating = k_gpt4o.rate_story(text)

            attempts += 1

    else:
        title = "Sample Title"
        text = "Sample text for the story."
        print("-- BYPASSING REDDIT --")
        rating = 10

    if rating < ideal_rating:
        raise ValueError(f"Failed to find a good enough story after {max_attempts} attempts.")

    # ADD id to json file 
    with open(links_path, "a", encoding="utf-8") as file:
        file.write(f"{id}\n")

    print(f"-- SUBREDDIT :: {subreddit} --")
    print(f"-- TITLE :: {title} --")
    print(f"-- RATING :: {rating}/10 || ATTEMPTS :: {attempts} --")

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

    return story, title, subreddit, link


def prepare_audio(project, script_path):
    audio_path = f"{script_path}/projects/{project}/speech.mp3"
    duration = audio_duration(audio_path)
    print(f"-- DURATION : {duration} --")
    org_dur = duration

    for i in range(3):
        if duration >= 61:
            k_movie.speedupAudio(audio_path, duration)
            duration = audio_duration(audio_path)
        else:
            break
    
    if duration != org_dur:
        print(f"-- FINAL DURATION : {duration} --")

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
    total_length = k_movie.length_video(full_path)
    start_time = random.randint(0, int(total_length - duration))

    print(f"Start: {start_time} / Duration: {duration}")
    return full_path, start_time

def select_background_music(script_path):
    music_folder = os.path.join(script_path, "musics")
    files = [
        f for f in os.listdir(music_folder)
        if os.path.isfile(os.path.join(music_folder, f)) and f.endswith(".mp3") and f != ".gitkeep"
    ]

    if not files:
        raise FileNotFoundError("No music files found in the folder.")

    music_file = random.choice(files)
    print(f"-- MUSIC SELECTED : {music_file} --")

    return os.path.join(music_folder, music_file)


def create_final_video(project, video_path, start_time, duration, script_path):
    cropped = f"{script_path}/projects/{project}/video.mp4"
    audio = f"{script_path}/projects/{project}/speech_with_music.mp3"
    video_with_audio = f"{script_path}/projects/{project}/video_audio.mp4"
    sub_output = f"{script_path}/projects/{project}/video_subtitled.mp4"
    final_output = f"{script_path}/projects/{project}/video_final.mp4"
    srt_file = f"{script_path}/projects/{project}/speech.srt"

    k_movie.cropping(video_path, cropped, start_time, duration)
    k_movie.audio(cropped, audio, video_with_audio)
    k_movie.subtitles(srt_file, video_with_audio, sub_output)

    """--- Upscaling to 4K for YouTube ---"""
    k_movie.upscale_to_4k_youtube(sub_output, final_output)
    print("-- FINAL VIDEO GENERATED --")

def args():
    parser = argparse.ArgumentParser(description="Generate a video from a Reddit post.")
    parser.add_argument("--bp_r", action="store_true", help="Bypass Reddit fetching.")
    parser.add_argument("--bp_s", action="store_true", help="Bypass story generation.")
    parser.add_argument("--bp_a", action="store_true", help="Bypass audio generation.")
    parser.add_argument("--project", action="store_true", help="Use latest project.")
    return parser.parse_args()

def main():
    my_args = args()
    script_path = os.path.dirname(__file__)
    project = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")

    if my_args.project:
        projects_path = os.path.join(script_path, "projects")
        print(f"-- PROJECTS PATH : {projects_path} --")
        print(f"-- LIST OF PROJECTS --")
        for d in os.listdir(projects_path):
            if os.path.isdir(os.path.join(projects_path, d)):
                print(f"  - {d}")
        latest_folder = max(
            (os.path.join(projects_path, d) for d in os.listdir(projects_path) if os.path.isdir(os.path.join(projects_path, d))),
            key=os.path.getmtime,
            default=None
        )
        if latest_folder:
            project = os.path.basename(latest_folder)
            print(f"-- LATEST PROJECT : {project} --")
        else:
            print("No projects found.")
            exit(1)
        print(f"-- PROJECT : {project} --")
        reddit = "None"
    
    ensure_directories(script_path, project)

    if not my_args.project:
        attempts = 0
        max_attempts = 5

        while attempts < max_attempts:
            story, rtitle, reddit, link = fetch_and_generate_story(script_path, project, my_args.bp_r, my_args.bp_s, my_args.bp_a)

            if audio_duration(f"{script_path}/projects/{project}/speech.mp3") <= 66:
                break
            else:
                attempts += 1
                print(f"Audio too long, retrying... ({attempts}/{max_attempts})")
                
    else:
        story = "None"
        rtitle = "None"
        reddit = "None"

    audio_path, duration = prepare_audio(project, script_path)

    if not my_args.project:
        create_subtitles(project)
        k_gpt4o.correct_srt_file(project)
        k_srt.fix_srt_file(project)
        print("-- SRT CORRECTED --")

    music_path = select_background_music(script_path)
    combined_audio_path = os.path.join(script_path, "projects", project, "speech_with_music.mp3")
    k_movie.add_background_music(audio_path, music_path, combined_audio_path)

    video_path, start_time = select_background_video(duration, script_path)
    create_final_video(project, video_path, start_time, duration, script_path)

    title, description, tags = k_gpt4o.ytb(project, story, reddit, rtitle, link)
    print(f"-- TITLE : {title} --")
    print("-- DESCRIPTION AND TAGS GENERATED --")


    # Uncomment this to publish:
    k_youtube.publish(f"{script_path}/projects/{project}/video_final.mp4", title, description, tags)
    print(f'-- VIDEO PUBLISHED --')


if __name__ == "__main__":
    main()

    