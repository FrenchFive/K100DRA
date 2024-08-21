import os 
import k_reddit
import k_gpt4o
import k_srt
import random
import datetime

project = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
script_path = os.path.dirname(__file__)

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

k_srt.transcribe(project)
print("-- STR GENERATED --")

