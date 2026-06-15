"""The video engine.

This is the part the brief called out for "a full rework … better visuals and
text".  Compared to the old MoviePy path it produces:

* **Animated word-by-word captions** rendered with ASS/libass — the spoken word
  pops and lights up in the brand colour, with a thick outline + shadow for
  readability on any footage.
* **Colour grading** (contrast / saturation / vignette) for a richer image.
* **Subtle motion** so static stock clips feel alive.
* A small **brand watermark** and a **retention progress bar** that fills as the
  short plays.

Everything is ffmpeg, so it is fast and GPU-friendly.  ``-progress`` is parsed
so the UI shows a *real* render bar.  If the fancy path ever fails, a simple,
battle-tested fallback render still produces a watchable video.
"""

from __future__ import annotations

import os
import struct
import subprocess
from typing import Callable, List, Optional

from . import config

# Captions are authored at this resolution; the final file is upscaled after.
RENDER_W, RENDER_H = 1080, 1920
FINAL_W, FINAL_H = 2160, 3840

ProgressCb = Optional[Callable[[float, str], None]]


# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #
def supports_nvenc() -> bool:
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, check=True).stdout
        return "h264_nvenc" in out
    except Exception:
        return False


def _codec(use_gpu: bool) -> str:
    return "h264_nvenc" if use_gpu and supports_nvenc() else "libx264"


def probe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def _run(cmd: List[str], cwd: Optional[str] = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffmpeg failed").strip()[-500:])


def _run_progress(cmd: List[str], total: float, cb: ProgressCb,
                  lo: float, hi: float, cwd: Optional[str] = None) -> None:
    """Run ffmpeg, mapping its ``-progress`` output to ``[lo, hi]``."""
    full = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-progress", "pipe:1", "-nostats"] + cmd
    proc = subprocess.Popen(full, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    raw = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                seconds = raw / (1_000_000 if "us" in line else 1000)
                if total > 0 and cb:
                    cb(lo + (hi - lo) * min(1.0, seconds / total), None)
            elif line == "progress=end" and cb:
                cb(hi, None)
    finally:
        proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError((err or "ffmpeg failed").strip()[-500:])


# --------------------------------------------------------------------------- #
# Colour + font helpers
# --------------------------------------------------------------------------- #
def hex_to_ass(value: str, alpha: int = 0) -> str:
    """``#RRGGBB`` → ASS ``&HAABBGGRR`` (alpha 0 = opaque)."""
    v = value.lstrip("#")
    r, g, b = v[0:2], v[2:4], v[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def hex_to_ffmpeg(value: str) -> str:
    return "0x" + value.lstrip("#").upper()


def font_family_name(path: str) -> str:
    """Read the family name from an sfnt (ttf/otf) font's ``name`` table.

    libass matches fonts by family name, so we read it straight from the file
    instead of guessing — that's what keeps the captions from silently falling
    back to an ugly default face.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        num_tables = struct.unpack(">H", data[4:6])[0]
        name_off = None
        for i in range(num_tables):
            rec = 12 + i * 16
            tag = data[rec:rec + 4]
            if tag == b"name":
                name_off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
                break
        if name_off is None:
            return "Sans"
        count, str_off = struct.unpack(">HH", data[name_off + 2:name_off + 6])
        storage = name_off + str_off
        best = None
        for i in range(count):
            rec = name_off + 6 + i * 12
            pid, eid, lid, nid, length, offset = struct.unpack(">HHHHHH", data[rec:rec + 12])
            if nid not in (1, 16):
                continue
            raw = data[storage + offset:storage + offset + length]
            try:
                text = raw.decode("utf-16-be") if pid in (0, 3) else raw.decode("latin-1")
            except Exception:
                continue
            text = text.strip()
            if text:
                # Prefer the typographic family (nameID 16) when present.
                if nid == 16:
                    return text
                best = best or text
        return best or "Sans"
    except Exception:
        return "Sans"


# --------------------------------------------------------------------------- #
# ASS caption authoring
# --------------------------------------------------------------------------- #
def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(word: str) -> str:
    return word.replace("\\", "").replace("{", "(").replace("}", ")").strip()


def _group(words, size: int):
    return [words[i:i + size] for i in range(0, len(words), size)]


def build_ass(words, out_path: str, vis: "config.VisualStyle", font_family: str) -> str:
    """Write an ASS file with animated, word-highlighted captions."""
    fontsize = int(RENDER_H * 0.052)          # ~100px at 1080×1920
    margin_v = int(RENDER_H * 0.30)           # sit in the lower third
    primary = hex_to_ass(vis.caption_color)
    highlight = hex_to_ass(vis.caption_highlight)
    outline = hex_to_ass(vis.caption_outline)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {RENDER_W}
PlayResY: {RENDER_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{font_family},{fontsize},{primary},{highlight},{outline},&H64000000,-1,0,0,0,100,100,1,0,1,{vis.caption_outline_width},{vis.caption_shadow},2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: List[str] = []
    for phrase in _group(list(words), max(1, vis.caption_words_per_line)):
        n = len(phrase)
        for i, word in enumerate(phrase):
            start = word.start
            end = phrase[i + 1].start if i + 1 < n else max(word.end, word.start + 0.18)
            if end <= start:
                end = start + 0.12
            pieces = []
            for j, w in enumerate(phrase):
                token = _clean(w.text)
                if not token:
                    continue
                if j == i:
                    if vis.caption_pop:
                        pop = (r"{\c%s\fscx116\fscy116\t(0,130,\fscx100\fscy100)}%s{\rBase}"
                               % (highlight, token))
                    else:
                        pop = r"{\c%s}%s{\rBase}" % (highlight, token)
                    pieces.append(pop)
                else:
                    pieces.append(token)
            text = " ".join(pieces)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Base,,0,0,0,,{text}"
            )

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + "\n".join(events) + "\n")
    return out_path


# --------------------------------------------------------------------------- #
# Stream-clip overlay (handle, LIVE/CLIP badges, live chat)
# --------------------------------------------------------------------------- #
# Chat panel geometry (at 1080×1920), shared by the ASS author and the ffmpeg
# backdrop so they line up.
CHAT_X, CHAT_Y, CHAT_LINE_H, CHAT_W = 42, 660, 66, 600
# Chat-handle colours so usernames look like a real, varied chat.
CHAT_USER_COLORS = ["#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF", "#FF6FB5", "#C77DFF"]


def _ass_c(value: str) -> str:
    """``#RRGGBB`` → inline ASS colour ``&HBBGGRR&``."""
    v = value.lstrip("#")
    return f"&H{v[4:6]}{v[2:4]}{v[0:2]}&".upper()


def chat_panel() -> tuple:
    vis = config.settings.visuals
    k = max(1, vis.chat_lines_visible)
    return (CHAT_X - 16, CHAT_Y - 14, CHAT_W, k * CHAT_LINE_H + 24)


def _rolling_chat_events(messages, duration: float, k: int, chat6: str) -> List[str]:
    """Render chat as a rolling stack: newest at the bottom, scrolling up."""
    m = len(messages)
    if m == 0:
        return []
    t0, t1 = 1.4, max(3.0, duration - 1.4)
    times = [t0 + (t1 - t0) * i / m for i in range(m)] + [duration]
    events: List[str] = []
    for i, (user, msg) in enumerate(messages):
        user_c = _ass_c(CHAT_USER_COLORS[i % len(CHAT_USER_COLORS)])
        for p in range(k):                      # p newer messages have arrived
            if i + p >= len(times) - 1:
                break
            seg_start = times[i + p]
            seg_end = times[i + p + 1]
            if seg_end <= seg_start:
                continue
            slot = k - 1 - p                     # bottom slot is newest
            y = CHAT_Y + slot * CHAT_LINE_H
            fade = r"\fad(120,0)" if p == 0 else ""
            text = (f"{{\\an7\\pos({CHAT_X},{y}){fade}\\c{user_c}}}{_clean(user)}"
                    f"{{\\c{chat6}}}: {_clean(msg)}")
            events.append(f"Dialogue: 1,{_ass_time(seg_start)},{_ass_time(seg_end)},Chat,,0,0,0,,{text}")
    return events


def build_overlay_ass(messages, duration: float, out_path: str, font_family: str) -> str:
    """Write the stream-UI ASS: handle, LIVE/CLIP badges and the live chat."""
    vis = config.settings.visuals
    accent6 = _ass_c(vis.accent_color)
    chat6 = _ass_c(vis.chat_color)
    k = max(1, vis.chat_lines_visible)
    full = _ass_time(duration)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {RENDER_W}
PlayResY: {RENDER_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Badge,{font_family},50,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,7,0,0,0,1
Style: Chat,{font_family},40,{chat6},&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: List[str] = []
    # With the facecam on, the handle + LIVE sit beside it as a stream
    # "nameplate"; otherwise the handle is the top-left badge.
    if vis.facecam and os.path.exists(config.settings.facecam_path()):
        hx, hy = 42 + vis.facecam_width + 26, 70
    else:
        hx, hy = 42, 46
    events.append(f"Dialogue: 2,0:00:00.00,{full},Badge,,0,0,0,,{{\\an7\\pos({hx},{hy})\\c{accent6}}}{_clean(vis.handle)}")
    if vis.live_badge:
        events.append(f"Dialogue: 2,0:00:00.00,{full},Badge,,0,0,0,,{{\\an7\\pos({hx},{hy + 60})\\fscx80\\fscy80\\c&H3D2EFF&}}● LIVE")
    if vis.clip_badge:
        events.append(f"Dialogue: 2,0:00:00.00,{full},Badge,,0,0,0,,{{\\an9\\pos(1038,52)\\fscx76\\fscy76}}CLIP")
    if vis.chat_overlay:
        events += _rolling_chat_events(list(messages or []), duration, k, chat6)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + "\n".join(events) + "\n")
    return out_path


# --------------------------------------------------------------------------- #
# Audio helpers (pydub)
# --------------------------------------------------------------------------- #
def audio_duration(path: str) -> float:
    dur = probe_duration(path)
    if dur > 0:
        return dur
    from pydub import AudioSegment  # lazy fallback
    return len(AudioSegment.from_file(path)) / 1000.0


def speedup_audio(path: str, target_seconds: float) -> float:
    """Gently speed up over-long narration to fit ``target_seconds``."""
    from pydub import AudioSegment
    audio = AudioSegment.from_file(path)
    current = len(audio) / 1000.0
    if current <= target_seconds:
        return current
    factor = current / target_seconds
    sped = audio.speedup(playback_speed=factor)
    sped.export(path, format="mp3")
    return len(sped) / 1000.0


def mix_music(speech_path: str, music_path: Optional[str], out_path: str, music_db: float) -> None:
    """Overlay (optional) background music under the narration."""
    from pydub import AudioSegment
    speech = AudioSegment.from_file(speech_path)
    if not music_path:
        speech.export(out_path, format="mp3")
        return
    music = AudioSegment.from_file(music_path)
    if len(music) < len(speech):
        music *= (len(speech) // len(music) + 1)
    music = music[:len(speech)] - abs(music_db)
    speech.overlay(music).export(out_path, format="mp3")


# --------------------------------------------------------------------------- #
# Render passes
# --------------------------------------------------------------------------- #
def _base_filter(vis: "config.VisualStyle") -> str:
    """Crop to 9:16, with optional motion drift + colour grade."""
    if vis.motion_zoom:
        chain = (
            f"scale={int(RENDER_W*1.1)}:{int(RENDER_H*1.1)}:force_original_aspect_ratio=increase,"
            f"crop={RENDER_W}:{RENDER_H}:"
            f"x='(iw-{RENDER_W})/2+34*sin(t/4)':y='(ih-{RENDER_H})/2+34*cos(t/5)'"
        )
    else:
        chain = (f"scale={RENDER_W}:{RENDER_H}:force_original_aspect_ratio=increase,"
                 f"crop={RENDER_W}:{RENDER_H}")
    if vis.color_grade:
        chain += ",eq=contrast=1.07:saturation=1.14:brightness=0.012,vignette=PI/5"
    chain += ",setsar=1,fps=30"
    return chain


def _stylize_base(src: str, out: str, start: float, duration: float,
                  vis: "config.VisualStyle", use_gpu: bool, cb: ProgressCb,
                  lo: float, hi: float) -> None:
    cmd = ["-ss", str(start), "-i", src, "-t", str(duration),
           "-vf", _base_filter(vis), "-an",
           "-c:v", _codec(use_gpu), "-pix_fmt", "yuv420p", out]
    _run_progress(cmd, duration, cb, lo, hi)


def _captions_pass(base_video: str, audio: str, out: str,
                   vis: "config.VisualStyle", duration: float, use_gpu: bool,
                   cb: ProgressCb, lo: float, hi: float, cwd: str,
                   draw_bar: bool = True, stream: bool = True,
                   has_chat: bool = False) -> None:
    """Compose captions + stream overlay + facecam + bar, then mux audio."""
    inputs = ["-i", base_video, "-i", audio]
    accent = hex_to_ffmpeg(vis.accent_color)

    # Point libass at our bundled fonts so the brand faces actually load
    # (they are not installed system-wide).
    parts = [f"[0:v]ass=captions.ass:fontsdir={config.FONTS_DIR}"]
    if stream and vis.chat_overlay and has_chat:
        px, py, pw, ph = chat_panel()
        parts.append(f"drawbox=x={px}:y={py}:w={pw}:h={ph}:color=black@0.34:t=fill")
    if stream and vis.stream_mode:
        parts.append(f"ass=overlay.ass:fontsdir={config.FONTS_DIR}")
    if vis.progress_bar and draw_bar:
        parts.append(f"drawbox=x=0:y=ih-14:w='iw*t/{duration:.3f}':h=14:color={accent}@0.95:t=fill")
    vchain = ",".join(parts)

    # A single image overlay: the facecam (brand recall) in stream mode, else the
    # optional static watermark.
    facecam = config.settings.facecam_path()
    watermark = config.settings.watermark_path()
    if stream and vis.facecam and os.path.exists(facecam):
        inputs += ["-i", facecam]
        frame = (f",pad=iw+16:ih+16:8:8:{accent}@1.0" if vis.facecam_frame else "")
        vchain += "[vbase];"
        vchain += (f"[2:v]scale={vis.facecam_width}:-1{frame},format=rgba[cam];"
                   f"[vbase][cam]overlay=40:40[vout]")
    elif vis.watermark and os.path.exists(watermark):
        inputs += ["-i", watermark]
        vchain += "[vbase];"
        vchain += (f"[2:v]scale=150:-1,format=rgba,"
                   f"colorchannelmixer=aa={vis.watermark_opacity}[wm];"
                   f"[vbase][wm]overlay=W-w-44:54[vout]")
    else:
        vchain += "[vout]"

    cmd = inputs + [
        "-filter_complex", vchain,
        "-map", "[vout]", "-map", "1:a:0",
        "-c:v", _codec(use_gpu), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out,
    ]
    _run_progress(cmd, duration, cb, lo, hi, cwd=cwd)


def _upscale(src: str, out: str, use_gpu: bool, duration: float,
             cb: ProgressCb, lo: float, hi: float) -> None:
    cmd = ["-i", src, "-vf", f"scale={FINAL_W}:{FINAL_H}:flags=lanczos",
           "-c:v", _codec(use_gpu), "-b:v", "45M", "-maxrate", "55M",
           "-bufsize", "90M", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out]
    _run_progress(cmd, duration, cb, lo, hi)


def _basic_render(src: str, audio: str, srt_path: str, out: str,
                  start: float, duration: float, use_gpu: bool) -> None:
    """Dependable fallback: crop, mux audio, burn plain SRT, upscale-ish."""
    base = out.replace(".mp4", "_b.mp4")
    _run(["ffmpeg", "-y", "-ss", str(start), "-i", src, "-t", str(duration),
          "-vf", f"scale={RENDER_W}:{RENDER_H}:force_original_aspect_ratio=increase,"
                 f"crop={RENDER_W}:{RENDER_H}", "-an",
          "-c:v", _codec(use_gpu), "-pix_fmt", "yuv420p", base])
    fam = font_family_name(config.settings.font_path())
    style = f"FontName={fam},Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H000A0A0A,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=170"
    _run(["ffmpeg", "-y", "-i", base, "-i", audio,
          "-vf", f"subtitles={os.path.basename(srt_path)}:fontsdir={config.FONTS_DIR}:force_style='{style}'",
          "-map", "0:v:0", "-map", "1:a:0", "-c:v", _codec(use_gpu),
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out],
         cwd=os.path.dirname(srt_path))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def render_video(project: str, words, background, audio_path: str,
                 srt_path: str, use_gpu: bool, on_progress: ProgressCb = None,
                 chat=None) -> str:
    """Produce ``video_final.mp4`` for ``project`` and return its path."""
    pdir = config.project_dir(project)
    vis = config.settings.visuals
    base = os.path.join(pdir, "base.mp4")
    styled = os.path.join(pdir, "video_styled.mp4")
    final = os.path.join(pdir, "video_final.mp4")
    duration = background.duration
    has_chat = bool(chat)

    try:
        build_ass(words, os.path.join(pdir, "captions.ass"), vis,
                  font_family_name(config.settings.font_path()))
        if vis.stream_mode:
            build_overlay_ass(chat or [], duration, os.path.join(pdir, "overlay.ass"),
                              font_family_name(config.settings.chat_font_path()))

        if on_progress:
            on_progress(0.02, f"Styling background ({background.name})")
        _stylize_base(background.path, base, background.start, duration, vis,
                      use_gpu, on_progress, 0.02, 0.30)

        # Degrade gracefully: full stream look → drop bar → captions only.
        if on_progress:
            on_progress(0.30, "Burning captions + stream overlay")
        attempts = [
            dict(draw_bar=True, stream=True),
            dict(draw_bar=False, stream=True),
            dict(draw_bar=False, stream=False),
        ]
        last_exc = None
        for i, opts in enumerate(attempts):
            try:
                _captions_pass(base, audio_path, styled, vis, duration, use_gpu,
                               on_progress, 0.30, 0.78, cwd=pdir, has_chat=has_chat, **opts)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if on_progress and i + 1 < len(attempts):
                    on_progress(0.30, "Simplifying overlay and retrying captions")
        if last_exc is not None:
            raise last_exc

        if on_progress:
            on_progress(0.78, "Upscaling to 4K")
        _upscale(styled, final, use_gpu, duration, on_progress, 0.78, 1.0)
        return final
    except Exception as exc:
        if on_progress:
            on_progress(0.5, f"Fancy render failed ({str(exc)[:80]}); using fallback")
        _basic_render(background.path, audio_path, srt_path, final,
                      background.start, duration, use_gpu)
        if on_progress:
            on_progress(1.0, "Fallback render complete")
        return final
