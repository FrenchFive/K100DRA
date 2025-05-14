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
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a young female influencer. From the user prompt generate short script (45 sec long to read, less than 750 characters) of the story as if you wrote the script, modify if needed. You can modify a bit to make it better. No introduction or outro start directly to the story. The story must be written in english whatever the language of the prompt is. Make this as entertaining as possible for Youtube."},
            {"role": "system", "content": "Priowrity is to make the story as entertaining as possible, not to be 100% accurate. You can modify the story a bit if needed."},
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

def ytb(project, prompt):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a young female influencer telling the story of others. Write ONLY the description of the video for the given script, make it short, finish the descriptin by : '<!>' to mark the end of the description and the beginning of the tags, then write the tags for the video, each sepeated by commas"},
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    result = completion.choices[0].message.content.strip()

    data = str(result).split("<!>")
    description = data[0]
    
    # Strip whitespace from each tag in the list
    tags = [tag.strip() for tag in data[1].split(',')]

    with open(f'{script_path}/projects/{project}/description.txt','w', encoding='utf-8') as file:
        file.write(f'{description} \n \n {tags}')

    return description, tags

def rate_story(story_text):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # Cheap model
        messages=[
            {"role": "system", "content": "You're an expert in viral YouTube storytelling. Rate the following story from 0 to 10 based on how engaging, entertaining, or emotionally impactful it would be as a short-form video. ONLY OUTPUT THE GRADE"},
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
            {"role": "system", "content": "Correct the SRT file to match the original text. The SRT file is in the first part and the original text is in the second part. Make sure that the SRT file matches the original text. Adding missing words and ONLY SEND THE SRT OUTPUT. Make sure everyword as at least few frames of appearance even if that means moving around the timings."},
            {"role": "user", "content": f"{content}\n\n{original_text}"}
        ]
    )
    result = response.choices[0].message.content.strip()

    #rename the original srt file
    os.rename(srt_file_path, f"{srt_file_path}.bak")

    with open(srt_file_path, 'w', encoding='utf-8') as file:
        file.write(result)

