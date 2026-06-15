"""The end-to-end pipeline.

Pure orchestration: it wires the modules together and reports every step through
a :class:`~k100dra.events.ProgressReporter`.  It knows nothing about the web or
the terminal, which keeps it easy to drive from either.
"""

from __future__ import annotations

import datetime
import os
import time
from typing import Optional

from . import config, llm, logs, reddit_source, selector, subtitles, video, voice, youtube
from .events import ProgressReporter, RunCancelled


def new_project_id() -> str:
    return datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")


def _artifact_url(project: str, filename: str) -> str:
    return f"/artifacts/{project}/{filename}"


def run(reporter: ProgressReporter, project: Optional[str] = None,
        upload: Optional[bool] = None) -> dict:
    """Run the whole pipeline. Returns a summary dict; never raises for a normal
    stage failure (it records the error on the stage instead)."""
    config.ensure_dirs()
    project = project or reporter.state.project
    config.project_dir(project)
    logs.init_run_log(project)
    s = config.settings
    upload = s.auto_upload if upload is None else upload
    summary: dict = {"project": project}

    try:
        # 1 — STORY ---------------------------------------------------------- #
        reporter.start("story", "Hunting for a story worth telling…")
        post, rating = _find_story(reporter)
        reddit_source.mark_used(post.id)
        reporter.artifact("story", "title", post.title)
        reporter.artifact("story", "subreddit", post.subreddit)
        reporter.artifact("story", "rating", rating)
        reporter.log(f"Found r/{post.subreddit} · “{post.title[:60]}” · {rating}/10")

        reporter.progress("story", 0.45, "K100DRA is writing the script…")
        buf = {"t": ""}

        def on_token(delta: str):
            buf["t"] += delta
            reporter.state.stages["story"].artifacts["text"] = buf["t"]
            frac = 0.45 + min(0.5, len(buf["t"]) / max(1, s.max_script_chars) * 0.5)
            reporter.progress("story", frac)

        script = llm.storyfy(post.title, post.text, project, on_token=on_token)
        reporter.artifact("story", "text", script)
        reporter.done("story", f"{len(script)} characters")
        summary["title"] = post.title

        # 2 — VOICE ---------------------------------------------------------- #
        reporter.check_stop()
        reporter.start("voice", "Recording the voiceover…")
        info = voice.synthesize(script, project,
                                on_progress=lambda f, m: reporter.progress("voice", f, m))
        reporter.artifact("voice", "engine", info["engine"])
        reporter.artifact("voice", "voice", info["voice"])
        reporter.artifact("voice", "audio_url", _artifact_url(project, "speech.mp3"))
        reporter.done("voice", f"via {info['engine']}")

        # 3 — AUDIO MIX ------------------------------------------------------ #
        reporter.check_stop()
        reporter.start("audio", "Fitting length + mixing music…")
        speech = os.path.join(config.project_dir(project), "speech.mp3")
        duration = video.audio_duration(speech)
        if duration > s.target_duration:
            reporter.progress("audio", 0.3, f"Trimming {duration:.0f}s → {s.target_duration:.0f}s")
            duration = video.speedup_audio(speech, s.target_duration)
        music = selector.select_music(duration=duration, log=reporter.log)
        mixed = os.path.join(config.project_dir(project), "speech_with_music.mp3")
        reporter.progress("audio", 0.7, "Adding background music" if music else "No music found")
        try:
            video.mix_music(speech, music.path if music else None, mixed, s.music_volume_db)
        finally:
            selector.cleanup(music)  # remove any fetched YouTube music segment
        duration = video.audio_duration(mixed)
        reporter.artifact("audio", "duration", round(duration, 1))
        reporter.artifact("audio", "audio_url", _artifact_url(project, "speech_with_music.mp3"))
        reporter.done("audio", f"{duration:.1f}s")

        # 4 — SUBTITLES ------------------------------------------------------ #
        reporter.check_stop()
        reporter.start("subtitles", "Timing every word…")
        words = subtitles.transcribe(project, on_progress=lambda f, m: reporter.progress("subtitles", f * 0.7, m))
        reporter.progress("subtitles", 0.8, "Polishing spelling…")
        words = subtitles.apply_correction(project, words, script)
        reporter.artifact("subtitles", "word_count", len(words))
        reporter.done("subtitles", f"{len(words)} words")

        # 5 — VIDEO ---------------------------------------------------------- #
        reporter.check_stop()
        reporter.start("video", "Choosing a fresh background…")
        background = selector.select_background(duration, log=reporter.log)
        reporter.artifact("video", "background", background.name)

        # Live-chat reactions for the stream overlay (best-effort).
        chat = []
        if config.settings.visuals.chat_overlay:
            reporter.progress("video", 0.01, "Spinning up the chat…")
            chat = llm.generate_chat(script)
            if chat:
                reporter.artifact("video", "chat", [f"{u}: {m}" for u, m in chat][:8])
                reporter.log(f"Chat overlay: {len(chat)} reactions")

        srt_path = os.path.join(config.project_dir(project), "speech.srt")
        try:
            video.render_video(
                project, words, background, mixed, srt_path, s.use_gpu,
                on_progress=lambda f, m: reporter.progress("video", f if f is not None else reporter.state.stages["video"].progress, m),
                chat=chat,
            )
        finally:
            selector.cleanup(background)  # remove any fetched YouTube segment
        preview = "video_styled.mp4" if os.path.exists(
            os.path.join(config.project_dir(project), "video_styled.mp4")) else "video_final.mp4"
        reporter.artifact("video", "video_url", _artifact_url(project, preview))
        reporter.artifact("video", "final_url", _artifact_url(project, "video_final.mp4"))
        reporter.done("video", background.name)
        summary["video"] = os.path.join(config.project_dir(project), "video_final.mp4")

        # 6 — PUBLISH -------------------------------------------------------- #
        reporter.check_stop()
        if not upload or not os.path.exists(youtube.CREDENTIALS_PATH):
            reporter.skip("publish", "auto-upload off" if not upload else "no youtube.json")
        else:
            reporter.start("publish", "Writing metadata…")
            title, description, tags = llm.metadata(script, post.subreddit, post.title, post.url)
            reporter.artifact("publish", "title", title)
            reporter.progress("publish", 0.25, "Uploading to YouTube…")
            url, scheduled = youtube.publish(
                summary["video"], title, description, tags,
                on_progress=lambda f, m: reporter.progress("publish", 0.25 + f * 0.75, m))
            reporter.artifact("publish", "youtube_url", url)
            reporter.artifact("publish", "scheduled", scheduled)
            reporter.done("publish", f"scheduled {scheduled}")
            summary.update({"youtube_url": url, "scheduled": scheduled})

        reporter.finish(summary, ok=True)
        return summary

    except RunCancelled:
        reporter.log("Run cancelled.", level="error")
        reporter.finish({"cancelled": True}, ok=False)
        return {"cancelled": True}
    except Exception as exc:  # surface on the active stage
        logs.get("pipeline").exception("run failed")
        active = next((st.id for st in reporter.state.stages.values()
                       if st.status.value == "running"), "story")
        reporter.error(active, str(exc))
        reporter.finish({"error": str(exc)}, ok=False)
        return {"error": str(exc)}


def _find_story(reporter: ProgressReporter):
    """Pull and rate posts until one clears the bar."""
    s = config.settings
    exclude = reddit_source.seen_ids()
    best = None
    for attempt in range(1, s.max_story_attempts + 1):
        reporter.check_stop()
        sub = reddit_source.random_subreddit()
        post = reddit_source.random_post(sub, exclude=exclude)
        if post is None:
            continue
        exclude.add(post.id)
        rating = llm.rate_story(f"{post.title}\n{post.text}")
        reporter.progress("story", min(0.4, attempt / s.max_story_attempts * 0.4),
                          f"r/{sub} scored {rating}/10 (try {attempt})")
        if rating >= s.min_story_rating:
            return post, rating
        reddit_source.mark_bad(post.id)
        if best is None or rating > best[1]:
            best = (post, rating)
    if best is not None:
        return best  # take the best we saw rather than failing the run
    raise RuntimeError(f"No usable story after {s.max_story_attempts} attempts.")
