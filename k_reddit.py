import praw
import os
import random

script_path = os.path.dirname(__file__)

import dotenv
dotenv.load_dotenv()

client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
user_agent = os.getenv("REDDIT_USER_AGENT")


reddit = praw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    user_agent=user_agent
)

def random_post(subreddit_name, project):
    subreddit = reddit.subreddit(subreddit_name)
    
    # Get a list of posts from the subreddit
    posts = list(subreddit.hot(limit=50))  # You can change the limit to get more posts
    
    # Choose a random post
    random_post = random.choice(posts)
    
    # Get the title and text
    title = random_post.title
    if random_post.selftext:  # Check if there's any text in the post
        text = random_post.selftext
    else:
        text = "[No text, this post might be a link or an image.]"

    post_url = f"https://www.reddit.com{random_post.permalink}"

    with open(f'{script_path}/projects/{project}/link.txt', 'w', encoding='utf-8') as file:
        file.write(post_url)
    
    return title, text