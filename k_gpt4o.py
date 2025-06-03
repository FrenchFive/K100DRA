import os
import openai

from dotenv import load_dotenv
load_dotenv()

KEY_OPENAI = os.getenv("KEY_OPENAI")
if KEY_OPENAI == None:
    print("Error: There is currently no 'KEY_OPENAI' environment variable. Please create a .env with the required values.")
    exit(1)

client = openai.OpenAI(api_key=KEY_OPENAI)

script_path = os.path.dirname(__file__)

def storyfier(prompt, project):
    completion = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "You are a young, relatable female influencer creating viral YouTube Shorts. From the user prompt, generate an engaging, entertaining script (about 50 seconds long, less than 1200 characters). Start with a strong hook in the first 1–2 seconds to grab attention. The tone should be expressive and natural, like you're speaking to a friend. Use drama, suspense, humor, or surprise to keep viewers watching until the end. Add one subtle question or call-to-action at the end to invite comments (e.g. 'What would you do?' or 'Have you ever seen this happen?'). No intros or outros—jump straight into the story. Accuracy is less important than storytelling. Make it entertaining and trendy. Write the beginning to hook the viewer attention."},
            {"role": "system", "content": "The goal is to boost retention and engagement. Feel free to modify the story to add suspense or humor. Use simple, clear language, and make it visually easy to follow. Use a conversational tone, like you're telling a secret or gossiping with a friend. End with a hook that encourages comments or shares."},
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    result = completion.choices[0].message.content.strip()
    with open(f'{script_path}/projects/{project}/generated.txt','w', encoding='utf-8') as file:
        file.write(result)
    return(result)


def audio(prompt, project):
    speech_file_path = f"{script_path}/projects/{project}/speech.mp3"
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="nova",
        input=prompt
    )

    response.stream_to_file(speech_file_path)

def ytb(project, prompt, reddit, rtitle, link):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a young YOUTUBE Shorts female influencer telling stories. Write a title for the given video, finish the title by '<!>', Make it short and impactful without it being too revealing. Write the description of the video for the given script, make it short, finish the descriptin by : '<!>' to mark the end of the description and the beginning of the tags, then write the tags for the video, each sepeated by commas. ONLY OUTPUT THE ASKED ELEMENTS AND NO MORE, seperate the title, description and tags by '<!>'. DO NOT SPECIFY THE CATEGORIES, no Title: or Description: or Tags:, none of that."},
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    result = completion.choices[0].message.content.strip()

    data = str(result).split("<!>")
    title = data[0].strip().replace('"','')
    description = data[1].strip()

    
    # Strip whitespace from each tag in the list
    tags = [tag.strip() for tag in data[2].split(',')]

    tags.append("reddit")
    tags.append(reddit)

    description += "\n"
    description += "\n" + f"REDDIT : r/{reddit}"
    description += "\n" + f"TITLE : {rtitle}"
    description += "\n" + f"LINK : {link}"
    description += "\n\n\n\n"

    descrpt_tags = ""
    for tag in tags:
        descrpt_tags += f"#{tag.strip().replace(" ","").lower()} "

    description += descrpt_tags

    with open(f'{script_path}/projects/{project}/description.txt','w', encoding='utf-8') as file:
        file.write(f'{title} \n \n {description} \n \n {tags}')

    return title, description, tags

def rate_story(story_text):
    response = client.chat.completions.create(
        model="gpt-4o-mini",  #gpt-3.5-turbo
        messages=[
            {"role": "system", "content": "You're an expert in viral YouTube storytelling. Rate the following story from 0 to 10 based on its potential to succeed as a YouTube Short. Consider these factors: 1) Does it have a strong hook within the first 1–2 seconds? 2) Is it emotionally engaging, surprising, funny, or dramatic? 3) Would it make people want to watch until the end? 4) Would it spark curiosity or comments? ONLY OUTPUT A SINGLE INTEGER SCORE from 0 to 10. No explanation."},
            {"role": "user", "content": story_text}
        ]
    )
    content = response.choices[0].message.content.strip()

    # Try to extract a number between 1 and 10
    for word in content.split():
        if word.isdigit():
            rating = int(word)
            if 0 <= rating <= 10:
                return rating

    # Fallback if not parsed correctly
    return 0

def correct_srt_file(project):
    srt_file_path = f"{script_path}/projects/{project}/speech.srt"
    with open(srt_file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    original_content = f"{script_path}/projects/{project}/generated.txt"
    with open(original_content, 'r', encoding='utf-8') as file:
        original_text = file.read()
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Correct the SRT file to match the original text. The SRT file is in the first part and the original text is in the second part. Make sure that the SRT file matches the original text. Adding missing words and correcting MISPELLED one. ONLY SEND THE SRT OUTPUT. If a word is missing or has no display time, add only 10 to 40 milliseconds or less and only modify the timing of THE element before, 1 before only, OTHERWISE dont touch the timings."},
            {"role": "user", "content": f"{content}\n\n{original_text}"}
        ]
    )
    result = response.choices[0].message.content.strip()

    #rename the original srt file
    os.rename(srt_file_path, f"{srt_file_path}.bak")

    with open(srt_file_path, 'w', encoding='utf-8') as file:
        file.write(result)

