# K100DRA

Scripting content creation using Python and AI

[YOUTUBE](https://www.youtube.com/@k100dra5/shorts) :: https://www.youtube.com/@k100dra5/shorts

## Functionnalities

- REDDIT :
    - Pick a random subreddit 
    - Searches HOT 50 posts (Hot : New and Popular)
    - Pick one random Post from the 50 
- AI :
    - Rewrite the text to match style, and lenght of the video
    - Generate an audio
    - From the audio generate automatic subtitles 
- VIDEO :
    - Trim a video randomly based on audio lenght 
    - Crop the video into a 9/16 format (Vertical format)
    - Add Subtitles to the middle of the screen 
    - Add the generated audio 
- YOUTUBE :
    - Uses Post Title as Video Title 
    - Based on Script, generates Description and Tags 
    - Automatic Upload

## REQUIREMENTS 


**PTDUB** : Manage Audio 
<br>```pip install pydub```

**PRAW** : Used to parse Reddit Data
<br>```pip install rawpy```
 
**OPENAI** : Manage AI functions 
<br>```pip install openai```

**MOVIEPY** : Allows to control Videos through Python
<br>```pip install moviepy```

**PYSRT** : Manage SRT file (Standart file format for Subtitles)
<br>```pip install pysrt```

**GOOGLE API** : Permit automatic upload to youtube 

**API KEY ARE NECESSARY FOR :**
- REDDIT : Client ID and Secret : ```reddit.secret```
- YOUTUBE : JSON App : ```youtube.json``` // Youtube Credentials will require a Web sign-in for the 1st time.
