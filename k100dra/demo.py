"""A fully simulated run.

Lets anyone watch the studio dashboard work end-to-end with **no API keys and no
ffmpeg** — perfect for trying the UI, screenshots, or development.  It emits the
exact same events as the real pipeline, just from canned data.
"""

from __future__ import annotations

import time

from . import logs
from .events import ProgressReporter, RunCancelled

SAMPLE_SCRIPT = (
    "Chat. CHAT. You are not ready for this one. So she finds a second phone taped "
    "under his desk drawer — and it's still WARM. She doesn't say a word. She "
    "photographs everything, puts it back exactly how it was, and waits. Someone "
    "in chat just said 'leave him' — okay hold on, it gets worse. Three days later "
    "he 'loses' that phone and tears the whole house apart looking for it. That's "
    "when she slides it across the table. The color just... drains out of his face. "
    "And chat, the phone wasn't even the worst part. The worst part was whose "
    "number kept calling. Be honest — would you have stayed calm, or lost it right "
    "there? ...yeah. That's the clip. That's going on the channel."
)

SAMPLE_CHAT = [
    "mossy_frog: NO WAY", "xX_dadbod_Xx: not the second phone 💀", "certified_yapper: LEAVE HIM",
    "pixel_gremlin: chat is this real", "soup_enjoyer: called it", "vibe_auditor: still WARM?? bro",
    "404_namegone: F", "lurkzilla: I'm screaming",
]


def _sleep(reporter: ProgressReporter, seconds: float, steps: int = 12):
    for _ in range(steps):
        reporter.check_stop()
        time.sleep(seconds / steps)


def run(reporter: ProgressReporter) -> dict:
    logs.init_run_log(reporter.state.project)
    try:
        # STORY — stream the script word by word.
        reporter.start("story", "Hunting for a story worth telling…")
        for i, sub in enumerate(["TIFU", "confessions", "TrueOffMyChest"], 1):
            reporter.progress("story", i / 8, f"r/{sub} scored {5 + i}/10 (try {i})")
            _sleep(reporter, 0.4)
        reporter.artifact("story", "title", "I found a second phone taped under his desk")
        reporter.artifact("story", "subreddit", "TrueOffMyChest")
        reporter.artifact("story", "rating", 9)
        reporter.progress("story", 0.45, "K100DRA is writing the script…")
        text = ""
        words = SAMPLE_SCRIPT.split(" ")
        for i, w in enumerate(words):
            reporter.check_stop()
            text += w + " "
            reporter.state.stages["story"].artifacts["text"] = text
            reporter.progress("story", 0.45 + 0.5 * (i + 1) / len(words))
            time.sleep(0.045)
        reporter.done("story", f"{len(text)} characters")

        # VOICE
        reporter.start("voice", "Recording the voiceover (ElevenLabs)…")
        for p in range(0, 101, 8):
            reporter.check_stop()
            reporter.progress("voice", p / 100, "Streaming voice…")
            time.sleep(0.08)
        reporter.artifact("voice", "engine", "elevenlabs (demo)")
        reporter.artifact("voice", "voice", "Rachel")
        reporter.done("voice", "via elevenlabs")

        # AUDIO
        reporter.start("audio", "Fitting length + mixing music…")
        reporter.progress("audio", 0.4, "Trimming 63s → 59s")
        _sleep(reporter, 0.5)
        reporter.progress("audio", 0.8, "Adding background music")
        _sleep(reporter, 0.4)
        reporter.artifact("audio", "duration", 58.6)
        reporter.done("audio", "58.6s")

        # SUBTITLES
        reporter.start("subtitles", "Timing every word…")
        for p in range(0, 101, 10):
            reporter.check_stop()
            reporter.progress("subtitles", p / 100, "Transcribing with Whisper…")
            time.sleep(0.06)
        reporter.artifact("subtitles", "word_count", len(words))
        reporter.done("subtitles", f"{len(words)} words")

        # VIDEO
        reporter.start("video", "Choosing a fresh background…")
        reporter.artifact("video", "background", "city_night_loop.mp4")
        reporter.artifact("video", "chat", SAMPLE_CHAT)
        reporter.log(f"Chat overlay: {len(SAMPLE_CHAT)} reactions")
        for label, lo, hi in [("Styling background", 0.02, 0.30),
                              ("Burning captions + stream overlay", 0.30, 0.78),
                              ("Upscaling to 4K", 0.78, 1.0)]:
            steps = 14
            for k in range(steps + 1):
                reporter.check_stop()
                reporter.progress("video", lo + (hi - lo) * k / steps, label)
                time.sleep(0.05)
        reporter.done("video", "city_night_loop.mp4")

        # PUBLISH
        reporter.start("publish", "Writing metadata…")
        reporter.artifact("publish", "title", "He hid a SECOND phone… you won't believe who called")
        reporter.progress("publish", 0.3, "Uploading to YouTube…")
        for p in range(30, 101, 10):
            reporter.check_stop()
            reporter.progress("publish", p / 100, f"Uploading… {p}%")
            time.sleep(0.07)
        reporter.artifact("publish", "scheduled", "demo — not really uploaded")
        reporter.done("publish", "scheduled (demo)")

        reporter.finish({"title": "Demo run complete", "demo": True}, ok=True)
        return {"demo": True}
    except RunCancelled:
        reporter.log("Demo cancelled.", level="error")
        reporter.finish({"cancelled": True}, ok=False)
        return {"cancelled": True}
