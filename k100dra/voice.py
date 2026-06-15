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
    """Create ``speech.mp3`` for ``project``. Returns info about the engine used."""
    out_path = os.path.join(config.project_dir(project), "speech.mp3")
    s = config.settings

    if s.elevenlabs_key:
        try:
            _elevenlabs(text, out_path, on_progress)
            return {"engine": "elevenlabs", "voice": s.elevenlabs_voice_id, "path": out_path}
        except Exception as exc:
            if on_progress:
                on_progress(0.0, f"ElevenLabs failed ({exc}); falling back to OpenAI")

    _openai_tts(text, out_path, on_progress)
    return {"engine": "openai", "voice": s.openai_tts_voice, "path": out_path}


# --------------------------------------------------------------------------- #
def _elevenlabs(text: str, out_path: str, on_progress: ProgressCb) -> None:
    import requests  # always available

    s = config.settings
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{s.elevenlabs_voice_id}/stream"
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


def _openai_tts(text: str, out_path: str, on_progress: ProgressCb) -> None:
    import openai  # lazy

    s = config.settings
    if not s.openai_key:
        raise RuntimeError("No ElevenLabs key and no OpenAI key — cannot generate voice.")
    if on_progress:
        on_progress(0.2, "Generating voice with OpenAI TTS…")
    client = openai.OpenAI(api_key=s.openai_key)
    with client.audio.speech.with_streaming_response.create(
        model="tts-1-hd", voice=s.openai_tts_voice, input=text,
    ) as response:
        response.stream_to_file(out_path)
    if on_progress:
        on_progress(1.0, "Voice ready")
