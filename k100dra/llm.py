"""Text generation: rating, scriptwriting, chat, metadata and subtitle cleanup.

Provider-agnostic: a model id starting with ``claude`` routes to Anthropic,
anything else to OpenAI. If a configured model fails (wrong id / no access) the
call transparently falls back to ``fallback_text_model`` so a run never dies on
a model name. Prompts all come from the :mod:`persona`. SDKs are imported lazily.
"""

from __future__ import annotations

import os
import re
from typing import Callable, List, Optional, Tuple

from . import config, logs
from .persona import persona

_openai_client = None
_anthropic_client = None

_TAG_RE = re.compile(r"\[[^\]]*\]")
_DASH_RE = re.compile(r"\s*[—–]\s*")
_SP_HYPHEN_RE = re.compile(r"\s+-\s+")


def strip_tags(text: str) -> str:
    """Remove [performance tags] for the on-screen / subtitle version."""
    return re.sub(r"\s{2,}", " ", _TAG_RE.sub("", text)).strip()


def humanize(text: str) -> str:
    """Kill AI tells: replace em/en dashes and spaced hyphens with commas."""
    text = _DASH_RE.sub(", ", text)
    text = _SP_HYPHEN_RE.sub(", ", text)
    text = re.sub(r",\s*,", ", ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r",\s*([.!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


# Second-speaker interjections the writer marks as {chat: ...}.
_CHAT_RE = re.compile(r"\{chat:\s*(.*?)\}", re.I | re.S)


def flatten_markers(text: str) -> str:
    """Remove {chat: ...} braces but keep the spoken words (single-voice TTS)."""
    return _CHAT_RE.sub(lambda m: m.group(1).strip(), text)


def clean_for_display(text: str) -> str:
    """Tag-free, marker-free text for captions / subtitles (words kept, in order)."""
    return strip_tags(flatten_markers(text))


def display_script(text: str) -> str:
    """Tag-free text for the UI script panel, with chat interjections shown
    distinctly so you can see the second speaker."""
    text = _CHAT_RE.sub(lambda m: f"\n💬 {m.group(1).strip()}\n", strip_tags(text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def voice_segments(text: str):
    """Split a script into (speaker, text) segments: 'k' = K100DRA, 'chat' = a
    chat member's voiced interjection."""
    segments, last = [], 0
    for m in _CHAT_RE.finditer(text):
        pre = text[last:m.start()].strip()
        if pre:
            segments.append(("k", pre))
        msg = strip_tags(m.group(1)).strip()
        if msg:
            segments.append(("chat", msg))
        last = m.end()
    tail = text[last:].strip()
    if tail:
        segments.append(("k", tail))
    return segments or [("k", text.strip())]


# --------------------------------------------------------------------------- #
# Provider clients
# --------------------------------------------------------------------------- #
def _get_openai():
    global _openai_client
    if _openai_client is None:
        import openai  # lazy
        if not config.settings.openai_key:
            raise RuntimeError("KEY_OPENAI is not set — cannot reach OpenAI.")
        _openai_client = openai.OpenAI(api_key=config.settings.openai_key)
    return _openai_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic  # lazy
        if not config.settings.anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set — cannot reach Anthropic.")
        _anthropic_client = anthropic.Anthropic(api_key=config.settings.anthropic_key)
    return _anthropic_client


def _route(model: str, system: str, user: str, temperature: float,
           max_tokens: int, on_token: Optional[Callable[[str], None]]) -> str:
    if model.lower().startswith("claude"):
        return _anthropic_complete(model, system, user, temperature, max_tokens, on_token)
    return _openai_complete(model, system, user, temperature, max_tokens, on_token)


def _complete(model: str, system: str, user: str, temperature: float = 0.7,
              max_tokens: int = 1024, on_token: Optional[Callable[[str], None]] = None) -> str:
    """Run a chat completion, falling back to a known-good model on failure."""
    try:
        return _route(model, system, user, temperature, max_tokens, on_token)
    except Exception as exc:
        fb = config.settings.fallback_text_model
        if model != fb:
            logs.get("llm").warning("model %r failed (%s); falling back to %s",
                                    model, str(exc)[:160], fb)
            return _route(fb, system, user, temperature, max_tokens, on_token)
        raise


def _openai_complete(model, system, user, temperature, max_tokens, on_token) -> str:
    client = _get_openai()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if on_token is not None:
        text = ""
        stream = client.chat.completions.create(
            model=model, messages=messages, stream=True, temperature=temperature)
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                text += delta
                on_token(delta)
        return text
    resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    return resp.choices[0].message.content or ""


def _anthropic_complete(model, system, user, temperature, max_tokens, on_token) -> str:
    client = _get_anthropic()
    if on_token is not None:
        text = ""
        with client.messages.stream(model=model, system=system, max_tokens=max_tokens,
                                    temperature=temperature,
                                    messages=[{"role": "user", "content": user}]) as stream:
            for delta in stream.text_stream:
                text += delta
                on_token(delta)
        return text
    resp = client.messages.create(model=model, system=system, max_tokens=max_tokens,
                                  temperature=temperature,
                                  messages=[{"role": "user", "content": user}])
    return "".join(getattr(b, "text", "") for b in resp.content)


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
def rate_story(text: str) -> int:
    """Return a 0-10 viral-potential score for a raw story."""
    content = _complete(config.settings.model_rate, persona.rating_system_prompt(),
                        text[:6000], temperature=0.0, max_tokens=8)
    for token in re.findall(r"\d+", content):
        value = int(token)
        if 0 <= value <= 10:
            return value
    return 0


def storyfy(title: str, body: str, project: str,
            on_token: Optional[Callable[[str], None]] = None, chat=None,
            kind: str = "story") -> str:
    """Rewrite a story/news item into a K100DRA script (streamed if ``on_token``)."""
    s = config.settings
    system = persona.story_system_prompt(s.target_duration, s.max_script_chars,
                                         chat_samples=chat, kind=kind,
                                         voiced_chat=s.chat_voice)
    if kind == "news":
        user = f"HEADLINE: {title}\n\nWHAT PEOPLE ARE SAYING:\n{body}"[:8000]
    else:
        user = f"{title}\n\n{body}"[:8000]
    text = _complete(s.model_story, system, user, temperature=0.9, max_tokens=1100, on_token=on_token)

    # Remove dashes (AI tell), keep performance tags + {chat:} markers for voice.
    text = humanize(text.strip().strip('"'))
    path = os.path.join(config.project_dir(project), "generated.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(clean_for_display(text))
    return text


def generate_chat(script: str, count: int = 12) -> List[Tuple[str, str]]:
    """Generate fake live-chat reactions. Never fatal (returns [] on error)."""
    try:
        content = _complete(config.settings.model_rate, persona.chat_system_prompt(count),
                            script, temperature=1.0, max_tokens=600)
        out: List[Tuple[str, str]] = []
        for line in content.splitlines():
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
    raw = _complete(config.settings.model_meta, persona.metadata_system_prompt(),
                    script, temperature=0.7, max_tokens=500).strip()
    parts = [p.strip() for p in raw.split("<!>")]
    title = parts[0] if parts else ""
    # Strip a leading "Title:" label, quotes and angle brackets (YouTube rejects < >).
    title = re.sub(r"^\s*title\s*[:\-]\s*", "", title, flags=re.I)
    title = title.replace('"', "").replace("<", "").replace(">", "").strip()
    if not title:
        title = (source_title or "Story time").strip()[:95]
    description = parts[1].strip() if len(parts) > 1 else ""
    tags = [t.strip() for t in parts[2].split(",")] if len(parts) > 2 else []
    tags = [t for t in tags if t]

    if subreddit and subreddit.lower() != "none":
        tags += ["reddit", subreddit]
    hashtags = " ".join(f"#{t.replace(' ', '').lower()}" for t in tags[:8])
    description = (f"{description}\n\nStory via r/{subreddit}\n{link}\n\n{hashtags}").strip()
    return title, description, tags


def correct_srt(srt_text: str, script_text: str) -> str:
    """Fix spelling/missing words in an SRT against the original script."""
    system = (
        "Correct the SRT so its words match the reference script: fix misspellings and "
        "obvious transcription errors only. Keep the same number of cues and the exact same "
        "timings unless a cue is clearly empty. Output ONLY the SRT."
    )
    return _complete(config.settings.model_srt, system,
                     f"SRT:\n{srt_text}\n\nREFERENCE SCRIPT:\n{script_text}",
                     temperature=0.0, max_tokens=4000).strip()
