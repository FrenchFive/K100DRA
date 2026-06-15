"""Reddit story sourcing.

Fetches candidate posts and keeps a memory of what has already been used (or
rejected) so the channel never repeats itself.  ``praw`` is imported lazily.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import List, Optional, Set

from . import config

SUBREDDITS = [
    "TrueOffMyChest", "todayilearned", "TIFU", "confessions", "FanTheories",
    "TalesFromRetail", "decidingtobebetter", "offmychest", "confession", "FML",
    "AmItheAsshole", "BestofRedditorUpdates", "MadeMeSmile", "funfacts",
    "UnpopularOpinion", "tifu", "EntitledPeople", "pettyrevenge", "ProRevenge",
]

_reddit = None


def _client():
    global _reddit
    if _reddit is None:
        import praw  # lazy
        s = config.settings
        if not (s.reddit_client_id and s.reddit_client_secret):
            raise RuntimeError("Reddit credentials are not configured.")
        _reddit = praw.Reddit(
            client_id=s.reddit_client_id,
            client_secret=s.reddit_client_secret,
            user_agent=s.reddit_user_agent or "K100DRA",
        )
    return _reddit


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    text: str
    url: str


# --- usage memory ---------------------------------------------------------- #
def _read_ids(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip()}


def seen_ids() -> Set[str]:
    return _read_ids(config.LINKS_FILE) | _read_ids(config.BAD_LINKS_FILE)


def mark_used(post_id: str) -> None:
    with open(config.LINKS_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{post_id}\n")


def mark_bad(post_id: str) -> None:
    with open(config.BAD_LINKS_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{post_id}\n")


# --- fetching -------------------------------------------------------------- #
def random_post(subreddit_name: str, exclude: Optional[Set[str]] = None) -> Optional[Post]:
    exclude = exclude or set()
    subreddit = _client().subreddit(subreddit_name)
    posts = [p for p in subreddit.hot(limit=100)
             if p.id not in exclude and getattr(p, "selftext", "").strip()
             and not p.over_18 and not p.stickied]
    if not posts:
        return None
    chosen = random.choice(posts)
    return Post(
        id=chosen.id,
        subreddit=subreddit_name,
        title=chosen.title,
        text=chosen.selftext,
        url=f"https://www.reddit.com{chosen.permalink}",
    )


def random_subreddit() -> str:
    return random.choice(SUBREDDITS)
