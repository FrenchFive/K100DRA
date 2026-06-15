"""A simple console sink for headless runs.

Turns pipeline events into clean, single-line progress output without any extra
dependencies (so ``main.py`` works even where ``rich`` isn't installed).
"""

from __future__ import annotations

import sys


class ConsoleReporter:
    """Pass ``ConsoleReporter().sink`` as the ProgressReporter sink."""

    def __init__(self) -> None:
        self._last_line = ""
        self._seen_logs = 0

    def sink(self, event_type: str, state: dict) -> None:
        # Print any new log lines.
        logs = state.get("logs", [])
        for entry in logs[self._seen_logs:]:
            prefix = "  ✖" if entry.get("level") == "error" else "  ·"
            sys.stdout.write(f"\r{' ' * len(self._last_line)}\r")
            print(f"{prefix} {entry['msg']}")
            self._last_line = ""
        self._seen_logs = len(logs)

        # Live overall bar.
        overall = state.get("overall", 0) or 0
        active = next((s for s in state.get("stages", []) if s["status"] == "running"), None)
        eta = state.get("eta")
        bar_len = 24
        filled = int(bar_len * overall)
        bar = "█" * filled + "░" * (bar_len - filled)
        label = (active["message"] or active["label"]) if active else state.get("status", "")
        eta_txt = f" ~{int(eta)}s" if eta else ""
        line = f"  [{bar}] {int(overall * 100):3d}% {label}{eta_txt}"
        self._last_line = line
        sys.stdout.write("\r" + line[:120].ljust(len(self._last_line)))
        sys.stdout.flush()

        if event_type == "done":
            sys.stdout.write("\n")
            sys.stdout.flush()
