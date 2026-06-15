#!/usr/bin/env python3
"""Headless K100DRA runner.

For the live dashboard use ``python run_studio.py`` instead.  This script runs
the same pipeline from the terminal — handy for cron jobs and batch generation.

    python main.py                 # make one video
    python main.py -n 5            # make five
    python main.py --no-upload     # render but don't upload
    python main.py --demo          # simulate a run (no keys / ffmpeg needed)
"""

from __future__ import annotations

import argparse
import datetime
import time

from k100dra import config, demo as demo_mod, pipeline
from k100dra.console import ConsoleReporter
from k100dra.events import ProgressReporter, RunState
from k100dra.persona import persona


def run_once(demo: bool, upload: bool) -> dict:
    project = "demo" if demo else pipeline.new_project_id()
    state = RunState(run_id=project, project=project, demo=demo)
    reporter = ProgressReporter(state, sink=ConsoleReporter().sink)
    if demo:
        return demo_mod.run(reporter)
    return pipeline.run(reporter, project, upload=upload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate K100DRA shorts from the terminal.")
    parser.add_argument("-n", "--count", type=int, default=1, help="How many videos to make.")
    parser.add_argument("--no-upload", action="store_true", help="Render but skip YouTube upload.")
    parser.add_argument("--demo", action="store_true", help="Run a simulated pipeline (no keys/ffmpeg).")
    parser.add_argument("--cpu", action="store_true", help="Force CPU encoding.")
    args = parser.parse_args()

    if args.cpu:
        config.settings.use_gpu = False

    print(f"\n  🎬  {persona.name} — {persona.tagline}")
    ready = config.readiness()
    if not args.demo and not ready["can_run_real"]:
        missing = [c["label"] for c in ready["checks"].values() if not c["ok"] and not c.get("optional")]
        print(f"  ⚠  Missing setup: {', '.join(missing)}.  Use --demo to preview the pipeline.\n")

    start = time.time()
    successes = 0
    for i in range(1, args.count + 1):
        print(f"\n  ── run {i}/{args.count} ──")
        result = run_once(demo=args.demo, upload=not args.no_upload)
        if "error" not in result and "cancelled" not in result:
            successes += 1
            if result.get("youtube_url"):
                print(f"  ✅ {result['youtube_url']}")
            elif result.get("video"):
                print(f"  ✅ {result['video']}")
        else:
            print(f"  ✖ {result.get('error', 'cancelled')}")

    elapsed = datetime.timedelta(seconds=int(time.time() - start))
    print(f"\n  Done: {successes}/{args.count} succeeded in {elapsed}\n")


if __name__ == "__main__":
    main()
