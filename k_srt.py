from openai import OpenAI
import os
import re
from datetime import timedelta, datetime
import random

from dotenv import load_dotenv
load_dotenv()

KEY_OPENAI = os.getenv("KEY_OPENAI")
if KEY_OPENAI == None:
    print("Error: There is currently no 'KEY_OPENAI' environment variable. Please create a .env with the required values.")
    exit(1)

client = OpenAI(api_key=KEY_OPENAI)

script_path = os.path.dirname(__file__)

def add_punctuation_to_words(words, text):
    text_index = 0
    result = []

    for word_info in words:
        word = word_info.word  # dot notation
        start_index = text_index

        while text_index < len(text) and text[text_index:text_index+len(word)] != word:
            text_index += 1

        end_index = text_index + len(word)

        while end_index < len(text) and not text[end_index].isalnum():
            word += text[end_index]
            end_index += 1

        text_index = end_index

        result.append({
            'word': word.replace(' ', ''),
            'start': word_info.start,  # dot notation
            'end': word_info.end       # dot notation
        })

    return result


def format_time(seconds):
    """ Convert seconds to SRT time format (HH:MM:SS,mmm) """
    millis = int(seconds * 1000)
    hours = millis // 3600000
    minutes = (millis % 3600000) // 60000
    seconds = (millis % 60000) // 1000
    millis = millis % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

def should_start_new_chunk(word, next_word, punctuation_marks, time_gap_threshold, current_chunk_length, max_words_per_chunk):
    """
    Determine whether to start a new chunk based on punctuation, time gaps, and word limit.
    """
    if current_chunk_length >= max_words_per_chunk:
        return True  # Start a new chunk if the max word limit is reached

    if word['word'][-1] in punctuation_marks:
        return True  # Start a new chunk after punctuation

    if next_word is not None:
        time_gap = next_word['start'] - word['end']
        if time_gap > time_gap_threshold:
            return True  # Start a new chunk if there's a significant pause

    return False

def transcribe(project, time_gap_threshold=0.5, max_words_per_chunk=1, punctuation_marks={'.', '?', '!', ','}):
    audio_path = f"{script_path}/projects/{project}/speech.mp3"
    audio_file= open(audio_path, "rb")
    transcription = client.audio.transcriptions.create(
        model="whisper-1", 
        file=audio_file,
        response_format='verbose_json',
        timestamp_granularities=["word"],
    )


    words = transcription.words
    text = transcription.text

    words = add_punctuation_to_words(words, text)

    # Initialize variables for SRT formatting
    srt_content = []
    index = 1
    chunk = []
    chunk_start_time = words[0]['start']
    
    for i, word in enumerate(words):
        chunk.append(word['word'])
        
        # Check if it's time to start a new chunk
        next_word = words[i + 1] if i + 1 < len(words) else None
        if should_start_new_chunk(word, next_word, punctuation_marks, time_gap_threshold, len(chunk), max_words_per_chunk) or i == len(words) - 1:
            chunk_end_time = word['end']
            
            # Format the SRT block
            start_time_str = format_time(chunk_start_time)
            end_time_str = format_time(chunk_end_time)
            srt_content.append(f"{index}\n{start_time_str} --> {end_time_str}\n{' '.join(chunk)}\n")
            
            # Reset for the next chunk
            index += 1
            chunk = []
            if next_word:
                chunk_start_time = next_word['start']
    
    # Save the SRT content to a file
    srt_file_path = f"{script_path}/projects/{project}/speech.srt"
    with open(srt_file_path, "w", encoding="utf-8") as srt_file:
        srt_file.write("\n".join(srt_content))

def srt_to_timedelta(t):
    return datetime.strptime(t, "%H:%M:%S,%f") - datetime(1900, 1, 1)

def timedelta_to_srt(td):
    return str(td + datetime(1900, 1, 1)).split(' ')[1][:-3].replace('.', ',')

def fix_srt_timing(blocks):
    for idx in range(1, len(blocks)):
        i, start, end, text = blocks[idx]
        prev_i, prev_start, prev_end, prev_text = blocks[idx - 1]

        if start == end:
            start_td = srt_to_timedelta(start)
            prev_start_td = srt_to_timedelta(prev_start)
            prev_end_td = srt_to_timedelta(prev_end)

            prev_duration = prev_end_td - prev_start_td
            max_new_duration = min(timedelta(seconds=0.5), prev_duration / 2)
            fix_duration = timedelta(milliseconds=random.randint(80, int(max_new_duration.total_seconds() * 1000)))

            # Adjust previous block's end time
            new_prev_end = start_td - fix_duration
            if new_prev_end <= prev_start_td:
                new_prev_end = prev_start_td + timedelta(milliseconds=10)
                fix_duration = start_td - new_prev_end

            # Update timings
            blocks[idx - 1] = (prev_i, prev_start, timedelta_to_srt(new_prev_end), prev_text)
            blocks[idx] = (i, timedelta_to_srt(start_td - fix_duration), timedelta_to_srt(start_td), text)
    return blocks

def rebuild_srt(blocks):
    srt_output = []
    for i, start, end, text_lines in blocks:
        srt_output.append(f"{i}\n{start} --> {end}\n" + "\n".join(text_lines) + "\n")
    return "\n".join(srt_output)

def fix_srt_file(project):
    try :
        srt_path = f"{script_path}/projects/{project}/speech.srt"
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_text = f.read()

        blocksli = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)\n(?=\d+\n|\Z)', srt_text, re.S)
        blocks = [(int(i), s, e, t.strip().splitlines()) for i, s, e, t in blocksli]

        fixed_blocks = fix_srt_timing(blocks)
        fixed_srt = rebuild_srt(fixed_blocks)

        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(fixed_srt)

    except :
        print("Error from CHATGPT - fixing original SRT")
        srt_path = f"{script_path}/projects/{project}/speech.srt.bak"
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_text = f.read()

        blocksli = re.findall(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)\n(?=\d+\n|\Z)', srt_text, re.S)
        blocks = [(int(i), s, e, t.strip().splitlines()) for i, s, e, t in blocksli]

        fixed_blocks = fix_srt_timing(blocks)
        fixed_srt = rebuild_srt(fixed_blocks)

        srt_path = f"{script_path}/projects/{project}/speech.srt"
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(fixed_srt)