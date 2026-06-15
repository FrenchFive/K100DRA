"""Whisper transcription → word-level subtitles.

Word-level timing is what makes the new captions feel alive (each word pops as
it is spoken), so the transcriber keeps the per-word timestamps around instead
of collapsing them into lines.  ``openai`` is imported lazily.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import config

ProgressCb = Optional[Callable[[float, str], None]]


@dataclass
class Word:
    text: str
    start: float
    end: float


def _client():
    import openai  # lazy
    if not config.settings.openai_key:
        raise RuntimeError("KEY_OPENAI is not set — cannot transcribe.")
    return openai.OpenAI(api_key=config.settings.openai_key)


def _attach_punctuation(words, full_text: str) -> List[Word]:
    """Re-attach punctuation that Whisper strips from word tokens."""
    idx = 0
    out: List[Word] = []
    for w in words:
        token = w.word
        while idx < len(full_text) and full_text[idx:idx + len(token)] != token:
            idx += 1
        end = idx + len(token)
        while end < len(full_text) and not full_text[end].isalnum() and full_text[end] != " ":
            token += full_text[end]
            end += 1
        idx = end
        out.append(Word(text=token.strip(), start=float(w.start), end=float(w.end)))
    return out


def transcribe(project: str, on_progress: ProgressCb = None) -> List[Word]:
    audio_path = os.path.join(config.project_dir(project), "speech.mp3")
    if on_progress:
        on_progress(0.2, "Transcribing with Whisper…")
    with open(audio_path, "rb") as fh:
        result = _client().audio.transcriptions.create(
            model=config.settings.model_transcribe,
            file=fh,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    words = _attach_punctuation(result.words, result.text)
    if on_progress:
        on_progress(0.8, f"{len(words)} words timed")
    _write_srt(project, words)
    return words


def _fmt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _write_srt(project: str, words: List[Word]) -> str:
    """Write a one-word-per-cue SRT (used for upload captions + GPT cleanup)."""
    lines = []
    for i, w in enumerate(words, start=1):
        end = max(w.end, w.start + 0.05)
        lines.append(f"{i}\n{_fmt(w.start)} --> {_fmt(end)}\n{w.text}\n")
    path = os.path.join(config.project_dir(project), "speech.srt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


_SRT_RE = re.compile(
    r"(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def _to_seconds(stamp: str) -> float:
    hh, mm, rest = stamp.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def parse_srt_words(srt_text: str) -> List[Word]:
    out: List[Word] = []
    for _, start, end, text in _SRT_RE.findall(srt_text):
        token = " ".join(text.split())
        if token:
            out.append(Word(text=token, start=_to_seconds(start), end=_to_seconds(end)))
    return out


def apply_correction(project: str, words: List[Word], script_text: str) -> List[Word]:
    """Optionally clean spelling against the script. Never breaks the run."""
    from . import llm
    srt_path = os.path.join(config.project_dir(project), "speech.srt")
    try:
        with open(srt_path, "r", encoding="utf-8") as fh:
            original = fh.read()
        corrected = llm.correct_srt(original, script_text)
        fixed_words = parse_srt_words(corrected)
        # Only trust the correction if it kept roughly the same words.
        if abs(len(fixed_words) - len(words)) <= max(3, len(words) * 0.15):
            with open(srt_path, "w", encoding="utf-8") as fh:
                fh.write(corrected)
            return fixed_words
    except Exception:
        pass
    return words
