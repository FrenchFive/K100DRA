import os
import openai
client = openai.OpenAI()

script_path = os.path.dirname(__file__)

def storyfier(prompt, project):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a young female influencer telling the story of others. From the user prompt generate short script (45 sec long to read, less than 750 characters) of the story as you were the one living it. You can modify a bit to make it better. No introduction or outro start directly to the story."},
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

def ytb(prompt):
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

    return description, tags


print(ytb("So, it was a random Tuesday, right? I was flipping through my old comic book collection, just having a chill day. I stopped at a Wolverine issue because, duh, he's a total badass. But then I saw it—Wolverine is only 5 foot 3 inches tall! Like, hold up, this fierce, claw-wielding superhero is almost my height? Suddenly, it hit me: Height doesn't define strength. There's this powerful guy defying all odds, and he’s proof that you don’t need to be a towering giant to make a massive impact. Now, whenever I feel small, I think, if Wolverine can be a hero, why can't I?"))