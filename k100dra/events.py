"""Progress model that drives the live studio UI.

The pipeline never talks to the web layer directly.  It calls a
:class:`ProgressReporter`, which keeps an authoritative :class:`RunState` and
pushes plain-dict events to a sink callback.  The web server turns those into
WebSocket frames; the headless runner prints them.  This keeps the pipeline
totally UI-agnostic and easy to test.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


# Ordered stages of a run, with relative weights used for the overall bar / ETA.
# Heavier stages (rendering) move the global bar more.
STAGE_DEFS: List[Dict[str, Any]] = [
    {"id": "story", "label": "Script", "weight": 12},
    {"id": "voice", "label": "Voice", "weight": 16},
    {"id": "audio", "label": "Audio mix", "weight": 6},
    {"id": "subtitles", "label": "Subtitles", "weight": 14},
    {"id": "video", "label": "Video", "weight": 42},
    {"id": "publish", "label": "Publish", "weight": 10},
]


@dataclass
class Stage:
    id: str
    label: str
    weight: float
    status: Status = Status.PENDING
    progress: float = 0.0           # 0..1 within the stage
    message: str = ""
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        elapsed = None
        if self.started_at:
            elapsed = (self.ended_at or time.time()) - self.started_at
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status.value,
            "progress": round(self.progress, 4),
            "message": self.message,
            "elapsed": round(elapsed, 1) if elapsed is not None else None,
            "artifacts": self.artifacts,
            "error": self.error,
        }


class RunState:
    """Authoritative snapshot of one run."""

    def __init__(self, run_id: str, project: str, demo: bool = False):
        self.run_id = run_id
        self.project = project
        self.demo = demo
        self.status = Status.RUNNING
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self.stages: Dict[str, Stage] = {
            d["id"]: Stage(id=d["id"], label=d["label"], weight=d["weight"])
            for d in STAGE_DEFS
        }
        self.logs: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}
        self._total_weight = sum(s.weight for s in self.stages.values())

    # --- derived values ---------------------------------------------------- #
    def overall_progress(self) -> float:
        done = sum(s.weight * s.progress for s in self.stages.values())
        return round(done / self._total_weight, 4) if self._total_weight else 0.0

    def eta_seconds(self) -> Optional[float]:
        frac = self.overall_progress()
        if frac <= 0.01 or self.status != Status.RUNNING:
            return None
        elapsed = time.time() - self.started_at
        remaining = elapsed / frac - elapsed
        return max(0.0, round(remaining, 0))

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "project": self.project,
            "demo": self.demo,
            "status": self.status.value,
            "started_at": self.started_at,
            "elapsed": round((self.ended_at or time.time()) - self.started_at, 1),
            "overall": self.overall_progress(),
            "eta": self.eta_seconds(),
            "stages": [self.stages[d["id"]].to_dict() for d in STAGE_DEFS],
            "logs": self.logs[-200:],
            "summary": self.summary,
        }


# Sink receives (event_type, payload) for every change.
Sink = Callable[[str, Dict[str, Any]], None]


class ProgressReporter:
    """Thread-safe handle the pipeline uses to report progress."""

    def __init__(self, state: RunState, sink: Optional[Sink] = None):
        self.state = state
        self._sink = sink
        self._lock = threading.RLock()
        self._stop = threading.Event()

    # cooperative cancellation -------------------------------------------- #
    def request_stop(self) -> None:
        self._stop.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def check_stop(self) -> None:
        if self._stop.is_set():
            raise RunCancelled()

    # internal emit -------------------------------------------------------- #
    def _emit(self, event_type: str = "state") -> None:
        if self._sink is None:
            return
        try:
            self._sink(event_type, self.state.to_dict())
        except Exception:
            pass

    # logging -------------------------------------------------------------- #
    def log(self, message: str, level: str = "info") -> None:
        with self._lock:
            self.state.logs.append({"t": time.time(), "level": level, "msg": message})
            if len(self.state.logs) > 400:
                self.state.logs = self.state.logs[-300:]
        self._emit("log")

    # stage lifecycle ------------------------------------------------------ #
    def start(self, stage_id: str, message: str = "") -> None:
        with self._lock:
            st = self.state.stages[stage_id]
            st.status = Status.RUNNING
            st.started_at = time.time()
            st.progress = 0.0
            st.message = message
        self.log(f"▶ {self.state.stages[stage_id].label}: {message}".rstrip(": "))
        self._emit()

    def progress(self, stage_id: str, fraction: float, message: Optional[str] = None) -> None:
        with self._lock:
            st = self.state.stages[stage_id]
            st.progress = max(0.0, min(1.0, fraction))
            if message is not None:
                st.message = message
        self._emit()

    def artifact(self, stage_id: str, key: str, value: Any) -> None:
        with self._lock:
            self.state.stages[stage_id].artifacts[key] = value
        self._emit()

    def done(self, stage_id: str, message: str = "") -> None:
        with self._lock:
            st = self.state.stages[stage_id]
            st.status = Status.DONE
            st.progress = 1.0
            st.ended_at = time.time()
            if message:
                st.message = message
        self._emit()

    def skip(self, stage_id: str, message: str = "skipped") -> None:
        with self._lock:
            st = self.state.stages[stage_id]
            st.status = Status.SKIPPED
            st.progress = 1.0
            st.ended_at = time.time()
            st.message = message
        self._emit()

    def error(self, stage_id: str, message: str) -> None:
        with self._lock:
            st = self.state.stages[stage_id]
            st.status = Status.ERROR
            st.ended_at = time.time()
            st.error = message
        self.log(f"✖ {self.state.stages[stage_id].label}: {message}", level="error")
        self._emit()

    # run lifecycle -------------------------------------------------------- #
    def finish(self, summary: Optional[Dict[str, Any]] = None, ok: bool = True) -> None:
        with self._lock:
            self.state.status = Status.DONE if ok else Status.ERROR
            self.state.ended_at = time.time()
            if summary:
                self.state.summary.update(summary)
        self._emit("done")


class RunCancelled(Exception):
    """Raised inside the pipeline when a stop has been requested."""
