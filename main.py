import os 

import k_reddit
import k_gpt4o
import k_srt
import k_movie
import k_youtube

import random
import datetime
from pydub import AudioSegment

project = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
script_path = os.path.dirname(__file__)

video_folder = f"{script_path}/videos"
if os.path.exists(video_folder)==False:
    os.mkdir(video_folder)

if os.path.exists(f'{script_path}/projects')==False:
    os.mkdir(f'{script_path}/projects')

os.mkdir(f'{script_path}/projects/{project}')

subreddits = ['TrueOffMyChest','todayilearned',"TIFU"]
subreddit = random.choice(subreddits)
print(f'-- SUBREDDIT :: {subreddit} --')

title, text = k_reddit.random_post(subreddit, project)
data = title + '\n' + text
print(f'-- {title} --')

story = k_gpt4o.storyfier(data, project)
print("-- STORY GENERATED --")

k_gpt4o.audio(story, project)
print("-- AUDIO GENERATED --")

audio_path = f"{script_path}/projects/{project}/speech.mp3"
audio = AudioSegment.from_file(audio_path)  # Replace with your file path
duration = len(audio) / 1000

k_srt.transcribe(project)
print("-- STR GENERATED --")


#GET VIDEO FILES
files_in_folder = [f for f in os.listdir(video_folder) if os.path.isfile(os.path.join(video_folder, f))]
if files_in_folder:
    video = random.choice(files_in_folder)
    print(f'-- VIDEO : {video} --')
    videolen = k_movie.len(f'{script_path}/videos/{video}')
    beg = random.randint(0, int(videolen-duration))
    print(f'Début : {beg} // Durée {duration}')
    k_movie.cropping(f'{script_path}/videos/{video}', f'{script_path}/projects/{project}/video.mp4', beg, duration)

    k_movie.audio(f'{script_path}/projects/{project}/video.mp4', f'{script_path}/projects/{project}/speech.mp3', f'{script_path}/projects/{project}/video_audio.mp4')

    k_movie.subtitles(f'{script_path}/projects/{project}/speech.srt',f'{script_path}/projects/{project}/video_audio.mp4',f'{script_path}/projects/{project}/video_subtitled.mp4')

    print('-- VIDEO GENERATED --')

    description, tags = k_gpt4o.ytb(project, story)

    k_youtube.publish(f'{script_path}/projects/{project}/video_subtitled.mp4', title, description, tags)
else:
    print('NO FILE IN VIDEO FOLDER')

