"""OpenAI text generation: rating, scriptwriting, metadata and subtitle cleanup.

All prompts come from the :mod:`persona`, so the channel's voice is defined in
one place.  ``openai`` is imported lazily so the rest of the app (and the demo
mode) works even when the SDK is not installed.
"""

from __future__ import annotations

import os
import re
from typing import Callable, List, Optional, Tuple

from . import config
from .persona import persona

_client = None


def _get_client():
    global _client
    if _client is None:
        import openai  # lazy
        if not config.settings.openai_key:
            raise RuntimeError("KEY_OPENAI is not set — cannot reach OpenAI.")
        _client = openai.OpenAI(api_key=config.settings.openai_key)
    return _client


# --------------------------------------------------------------------------- #
def rate_story(text: str) -> int:
    """Return a 0-10 viral-potential score for a raw story."""
    client = _get_client()
    resp = client.chat.completions.create(
        model=config.settings.model_rate,
        messages=[
            {"role": "system", "content": persona.rating_system_prompt()},
            {"role": "user", "content": text[:6000]},
        ],
    )
    content = resp.choices[0].message.content.strip()
    for token in re.findall(r"\d+", content):
        value = int(token)
        if 0 <= value <= 10:
            return value
    return 0


def storyfy(
    title: str,
    body: str,
    project: str,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    """Rewrite a story into a K100DRA narration script.

    If ``on_token`` is given the response is streamed and each text delta is
    forwarded, which lets the UI show the script being written live.
    """
    client = _get_client()
    s = config.settings
    messages = [
        {"role": "system", "content": persona.story_system_prompt(s.target_duration, s.max_script_chars)},
        {"role": "user", "content": f"{title}\n\n{body}"[:8000]},
    ]

    text = ""
    if on_token is not None:
        stream = client.chat.completions.create(
            model=s.model_story, messages=messages, stream=True, temperature=0.9,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                text += delta
                on_token(delta)
    else:
        resp = client.chat.completions.create(
            model=s.model_story, messages=messages, temperature=0.9,
        )
        text = resp.choices[0].message.content

    text = text.strip().strip('"')
    path = os.path.join(config.project_dir(project), "generated.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def generate_chat(script: str, count: int = 12) -> List[Tuple[str, str]]:
    """Generate fake live-chat reactions to the story (username, message).

    Powers the on-screen chat overlay. Never fatal: returns ``[]`` on any error
    so a missing chat overlay can't break a render.
    """
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=config.settings.model_rate,  # cheap model is plenty for chat
            messages=[
                {"role": "system", "content": persona.chat_system_prompt(count)},
                {"role": "user", "content": script},
            ],
            temperature=1.0,
        )
        out: List[Tuple[str, str]] = []
        for line in resp.choices[0].message.content.splitlines():
            line = line.strip().lstrip("-•0123456789. ").strip()
            if ":" in line:
                user, msg = line.split(":", 1)
                user, msg = user.strip(), msg.strip()
                if user and msg:
                    out.append((user[:24], msg[:80]))
        return out
    except Exception:
        return []


def metadata(script: str, subreddit: str, source_title: str, link: str) -> Tuple[str, str, List[str]]:
    """Generate title, description and tags for the upload."""
    client = _get_client()
    resp = client.chat.completions.create(
        model=config.settings.model_meta,
        messages=[
            {"role": "system", "content": persona.metadata_system_prompt()},
            {"role": "user", "content": script},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    parts = [p.strip() for p in raw.split("<!>")]
    title = (parts[0] if parts else "").replace('"', "").strip()
    description = parts[1].strip() if len(parts) > 1 else ""
    tags = [t.strip() for t in parts[2].split(",")] if len(parts) > 2 else []
    tags = [t for t in tags if t]

    # Provenance + hashtags appended to the description.
    if subreddit and subreddit.lower() != "none":
        tags += ["reddit", subreddit]
    hashtags = " ".join(f"#{t.replace(' ', '').lower()}" for t in tags[:8])
    description = (
        f"{description}\n\n"
        f"Story via r/{subreddit}\n{link}\n\n{hashtags}"
    ).strip()
    return title, description, tags


def correct_srt(srt_text: str, script_text: str) -> str:
    """Fix spelling/missing words in an SRT against the original script."""
    client = _get_client()
    resp = client.chat.completions.create(
        model=config.settings.model_srt,
        messages=[
            {"role": "system", "content": (
                "Correct the SRT so its words match the reference script: fix misspellings "
                "and obvious transcription errors only. Keep the same number of cues and the "
                "exact same timings unless a cue is clearly empty. Output ONLY the SRT."
            )},
            {"role": "user", "content": f"SRT:\n{srt_text}\n\nREFERENCE SCRIPT:\n{script_text}"},
        ],
    )
    return resp.choices[0].message.content.strip()
