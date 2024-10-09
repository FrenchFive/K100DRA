from openai import OpenAI
import os
client = OpenAI()

script_path = os.path.dirname(__file__)

def add_punctuation_to_words(words, text):
    # Start tracking the index in the original text
    text_index = 0
    result = []

    # Iterate over each word in the words list
    for word_info in words:
        word = word_info['word']
        start_index = text_index

        # Find the word in the text, starting from text_index
        while text_index < len(text) and text[text_index:text_index+len(word)] != word:
            text_index += 1

        # After finding the word, look for punctuation right after the word
        end_index = text_index + len(word)
        
        # Collect any punctuation following the word
        while end_index < len(text) and not text[end_index].isalnum():
            word += text[end_index]
            end_index += 1

        # Move the text_index to the end of the word and punctuation
        text_index = end_index
        
        # Add the word with punctuation, start, and end time back to the result list
        result.append({
            'word': word.replace(' ',''),
            'start': word_info['start'],
            'end': word_info['end']
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