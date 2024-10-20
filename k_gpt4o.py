import os
import openai
client = openai.OpenAI()

script_path = os.path.dirname(__file__)

def storyfier(prompt, project):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a young female influencer telling the story of others. From the user prompt generate short script (45 sec long to read, less than 750 characters) of the story as you were the one living it. You can modify a bit to make it better. No introduction or outro start directly to the story. The story must be written in english whatever the language of the prompt is. Make this as entertaining as possible for Youtube."},
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
