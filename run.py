#!/usr/bin/env python3
"""K100DRA — start here.

    python run.py

On the first run this guides you through setting EVERYTHING up (API keys,
connecting YouTube) and verifies every key is valid. Once you're set up it
verifies your keys and launches the studio. That's it.

    python run.py --reconfigure   # re-run setup and re-enter every key
    python run.py --skip-verify   # don't make validation API calls
    python run.py --studio        # skip the menu, go straight to the dashboard
    python run.py --headless      # skip the menu, make one video in the terminal
    python run.py --port 8000     # studio port
"""

from __future__ import annotations

import argparse
import sys

BANNER = r"""
   _  ___ ___ ___  ___  ___    _
  | |/ / |_  )  \|   \| _ \  /_\    K100DRA STUDIO
  | ' <   / / () | |) |   / / _ \   the streamer who reads
  |_|\_\ /___\__/|___/|_|_\/_/ \_\  your wildest stories to chat
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="K100DRA — guided setup + launch")
    parser.add_argument("--reconfigure", action="store_true", help="Re-run setup, re-enter every key.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip API key validation calls.")
    parser.add_argument("--studio", action="store_true", help="Go straight to the dashboard.")
    parser.add_argument("--headless", action="store_true", help="Make one video in the terminal.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print(BANNER)

    from k100dra import config, setup_wizard

    rd = config.readiness()
    needs_setup = args.reconfigure or not rd["can_run_real"]

    if needs_setup:
        print("  Let's get you set up. This only takes a minute.\n")
        rd = setup_wizard.ensure_ready(verify=not args.skip_verify, force=args.reconfigure)
    else:
        # Already configured — just verify everything still works.
        rd = setup_wizard.ensure_ready(verify=not args.skip_verify, force=False)

    config.reload()

    # --- choose what to do next ------------------------------------------- #
    if args.headless:
        return _headless()
    if args.studio:
        return _studio(args.host, args.port)

    if not sys.stdin.isatty():
        # Non-interactive shell: default to the studio.
        return _studio(args.host, args.port)

    print("\n  What now?")
    print("    [1] Open the studio dashboard   (recommended)")
    print("    [2] Make one video right here   (headless)")
    print("    [3] Quit")
    choice = input("  > ").strip() or "1"
    if choice == "2":
        _headless()
    elif choice == "3":
        print("  See you, chat. 👋")
    else:
        _studio(args.host, args.port)


def _studio(host: str, port: int) -> None:
    try:
        from k100dra.web.server import serve
    except ImportError as exc:
        print(f"\n  ✖ The studio needs the web packages ({exc.name}).")
        print("    Install them with:  pip install -r requirements.txt\n")
        return
    url = f"http://{'localhost' if host == '0.0.0.0' else host}:{port}"
    print(f"\n  🎬  Studio → {url}   (press Start, or ✨ Demo)\n")
    try:
        import threading
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    serve(host=host, port=port)


def _headless() -> None:
    from k100dra import pipeline
    from k100dra.console import ConsoleReporter
    from k100dra.events import ProgressReporter, RunState
    project = pipeline.new_project_id()
    state = RunState(run_id=project, project=project)
    reporter = ProgressReporter(state, sink=ConsoleReporter().sink)
    result = pipeline.run(reporter, project)
    if result.get("youtube_url"):
        print(f"\n  ✅ {result['youtube_url']}")
    elif result.get("video"):
        print(f"\n  ✅ {result['video']}")
    else:
        print(f"\n  ✖ {result.get('error', 'done')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled. Re-run `python run.py` any time. 👋\n")
        sys.exit(0)
