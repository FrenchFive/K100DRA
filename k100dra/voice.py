"""Voiceover generation.

Primary engine is **ElevenLabs** (much warmer, more expressive narration than
the previous OpenAI TTS).  If no ElevenLabs key is configured, or the request
fails, it transparently falls back to OpenAI TTS so a run never dies on the
voice step.  The ElevenLabs call is streamed so the UI can show real download
progress.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from . import config

ProgressCb = Optional[Callable[[float, str], None]]


def list_voices() -> list:
    """List the voices on the configured ElevenLabs account (name + id).

    Returns [] if there's no key or the request fails — so callers can show a
    "paste an ID" fallback.
    """
    s = config.settings
    if not s.elevenlabs_key:
        return []
    try:
        import requests
        r = requests.get("https://api.elevenlabs.io/v1/voices",
                         headers={"xi-api-key": s.elevenlabs_key}, timeout=15)
        if r.status_code != 200:
            return []
        return [{"voice_id": v.get("voice_id"), "name": v.get("name", ""),
                 "category": v.get("category", "")}
                for v in r.json().get("voices", []) if v.get("voice_id")]
    except Exception:
        return []


def synthesize(text: str, project: str, on_progress: ProgressCb = None) -> dict:
    """Create ``speech.mp3``. Uses a second voice for {chat: ...} interjections
    when ``chat_voice`` is on, falling back to a single voice on any issue.

    Performance tags ([excited], [whispers], ...) are kept only for ElevenLabs v3
    (which performs them); otherwise they are stripped so they're never read.
    """
    from . import llm
    out_path = os.path.join(config.project_dir(project), "speech.mp3")
    s = config.settings
    tags_ok = s.voice_tags and "v3" in (s.elevenlabs_model or "")

    segments = llm.voice_segments(text) if s.chat_voice else [("k", text)]
    multi = s.chat_voice and len(segments) > 1 and any(sp == "chat" for sp, _ in segments)

    if multi:
        try:
            engine = _synth_segments(segments, out_path, tags_ok, on_progress)
            return {"engine": engine, "voice": s.elevenlabs_voice_id, "tags": tags_ok,
                    "two_voice": True, "path": out_path}
        except Exception as exc:
            if on_progress:
                on_progress(0.0, f"two-voice failed ({exc}); using single voice")

    engine = _synth_one(llm.flatten_markers(text), out_path, "k", tags_ok, on_progress)
    return {"engine": engine, "voice": s.elevenlabs_voice_id, "tags": tags_ok, "path": out_path}


def _synth_one(text: str, out_path: str, speaker: str, tags_ok: bool,
               on_progress: ProgressCb) -> str:
    """Synthesize one chunk with the voice for ``speaker`` ('k' or 'chat')."""
    from . import llm
    s = config.settings
    if s.elevenlabs_key:
        try:
            vid = s.elevenlabs_chat_voice_id if speaker == "chat" else s.elevenlabs_voice_id
            _elevenlabs(text if tags_ok else llm.strip_tags(text), out_path, on_progress, vid)
            return "elevenlabs"
        except Exception as exc:
            if on_progress:
                on_progress(0.0, f"ElevenLabs failed ({exc}); OpenAI fallback")
    voice = s.openai_chat_tts_voice if speaker == "chat" else s.openai_tts_voice
    _openai_tts(llm.strip_tags(text), out_path, on_progress, voice)
    return "openai"


def _synth_segments(segments, out_path: str, tags_ok: bool, on_progress: ProgressCb) -> str:
    """Synthesize each segment with its speaker's voice and stitch them together."""
    from pydub import AudioSegment
    combined = AudioSegment.silent(duration=0)
    engine = "elevenlabs"
    n = len(segments)
    for i, (sp, seg_text) in enumerate(segments):
        seg_file = f"{out_path}.seg{i}.mp3"
        engine = _synth_one(seg_text, seg_file, sp, tags_ok, None)
        clip = AudioSegment.from_file(seg_file)
        gap = 160 if sp == "chat" else 70   # a beat around the interjection
        combined += clip + AudioSegment.silent(duration=gap)
        try:
            os.remove(seg_file)
        except Exception:
            pass
        if on_progress:
            on_progress((i + 1) / n, f"Recording voices… ({i + 1}/{n})")
    combined.export(out_path, format="mp3")
    return f"{engine}+chat"


# --------------------------------------------------------------------------- #
def _elevenlabs(text: str, out_path: str, on_progress: ProgressCb, voice_id: str = None) -> None:
    import requests  # always available

    s = config.settings
    vid = voice_id or s.elevenlabs_voice_id
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/stream"
    headers = {
        "xi-api-key": s.elevenlabs_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": s.elevenlabs_model,
        "voice_settings": {
            "stability": s.voice_stability,
            "similarity_boost": s.voice_similarity,
            "style": s.voice_style,
            "use_speaker_boost": s.voice_speaker_boost,
        },
    }
    params = {"output_format": "mp3_44100_128"}

    if on_progress:
        on_progress(0.05, "Contacting ElevenLabs…")

    with requests.post(url, headers=headers, json=payload, params=params,
                       stream=True, timeout=120) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        total = int(resp.headers.get("content-length", 0))
        written = 0
        with open(out_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=16384):
                if not chunk:
                    continue
                fh.write(chunk)
                written += len(chunk)
                if on_progress:
                    if total:
                        on_progress(min(0.99, written / total), "Streaming voice…")
                    else:
                        # Unknown length: creep toward 0.9 so the bar still moves.
                        on_progress(min(0.9, 0.1 + written / 1_500_000), "Streaming voice…")
    if on_progress:
        on_progress(1.0, "Voice ready")


def _openai_tts(text: str, out_path: str, on_progress: ProgressCb, voice: str = None) -> None:
    import openai  # lazy

    s = config.settings
    if not s.openai_key:
        raise RuntimeError("No ElevenLabs key and no OpenAI key — cannot generate voice.")
    if on_progress:
        on_progress(0.2, "Generating voice with OpenAI TTS…")
    client = openai.OpenAI(api_key=s.openai_key)
    with client.audio.speech.with_streaming_response.create(
        model="tts-1-hd", voice=voice or s.openai_tts_voice, input=text,
    ) as response:
        response.stream_to_file(out_path)
    if on_progress:
        on_progress(1.0, "Voice ready")
