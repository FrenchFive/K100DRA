"""The K100DRA Studio web server.

A small FastAPI app that runs the pipeline in a background thread and streams its
progress to the browser over WebSocket.  The dashboard shows the script being
written, the voice + audio being produced, the video rendering and the upload —
each with its own bar plus an overall bar and ETA.
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config, demo as demo_mod, pipeline
from ..events import ProgressReporter, RunState
from ..persona import persona

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")


class RunManager:
    """Owns the current run and the latest snapshot pushed to clients."""

    def __init__(self) -> None:
        self.reporter: Optional[ProgressReporter] = None
        self.thread: Optional[threading.Thread] = None
        self._latest: dict = {}
        self._seq = 0
        self._stop_all = False
        self.clients: Set[WebSocket] = set()

    # sink called from the pipeline thread -------------------------------- #
    def _sink(self, _event_type: str, state: dict) -> None:
        self._latest = state
        self._seq += 1

    @property
    def latest(self) -> dict:
        return self._latest

    @property
    def seq(self) -> int:
        return self._seq

    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self, demo: bool = False, upload: Optional[bool] = None, count: int = 1) -> dict:
        if self.is_running():
            return {"ok": False, "error": "A run is already in progress."}
        self._stop_all = False
        self.thread = threading.Thread(
            target=self._worker, args=(demo, upload, max(1, count)), daemon=True)
        self.thread.start()
        return {"ok": True}

    def stop(self) -> dict:
        self._stop_all = True
        if self.reporter:
            self.reporter.request_stop()
        return {"ok": True}

    def _worker(self, demo: bool, upload: Optional[bool], count: int) -> None:
        for _ in range(count):
            if self._stop_all:
                break
            project = "demo" if demo else pipeline.new_project_id()
            state = RunState(run_id=uuid.uuid4().hex[:8], project=project, demo=demo)
            self.reporter = ProgressReporter(state, sink=self._sink)
            self._sink("state", state.to_dict())
            try:
                if demo:
                    demo_mod.run(self.reporter)
                else:
                    pipeline.run(self.reporter, project, upload=upload)
            except Exception as exc:  # pragma: no cover - defensive
                self.reporter.log(f"Run crashed: {exc}", level="error")
            if self.reporter and self.reporter.stop_requested:
                break


manager = RunManager()
app = FastAPI(title="K100DRA Studio")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_broadcaster())


async def _broadcaster() -> None:
    """Coalesce rapid updates and fan them out to every connected client."""
    last_seq = -1
    while True:
        await asyncio.sleep(0.06)
        if manager.seq == last_seq or not manager.clients:
            last_seq = manager.seq
            continue
        last_seq = manager.seq
        payload = {"type": "state", "state": manager.latest}
        dead = []
        for ws in list(manager.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            manager.clients.discard(ws)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/readiness")
async def readiness() -> JSONResponse:
    data = config.readiness()
    data["persona"] = {"name": persona.name, "tagline": persona.tagline, "accent": persona.accent_color}
    data["running"] = manager.is_running()
    return JSONResponse(data)


@app.get("/api/state")
async def state() -> JSONResponse:
    return JSONResponse(manager.latest or {})


@app.post("/api/run")
async def run_real(payload: dict | None = None) -> JSONResponse:
    payload = payload or {}
    return JSONResponse(manager.start(
        demo=bool(payload.get("demo")),
        upload=payload.get("upload"),
        count=int(payload.get("count", 1)),
    ))


@app.post("/api/stop")
async def stop() -> JSONResponse:
    return JSONResponse(manager.stop())


@app.get("/artifacts/{project}/{filename}")
async def artifact(project: str, filename: str):
    # Guard against path traversal.
    safe = os.path.normpath(os.path.join(config.PROJECTS_DIR, project, filename))
    if not safe.startswith(os.path.abspath(config.PROJECTS_DIR)) or not os.path.exists(safe):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(safe)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    manager.clients.add(websocket)
    try:
        if manager.latest:
            await websocket.send_json({"type": "state", "state": manager.latest})
        while True:
            await websocket.receive_text()  # keep the socket open
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.clients.discard(websocket)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")
