#!/usr/bin/env python3
"""Launch the K100DRA Studio dashboard.

    python run_studio.py                # http://127.0.0.1:8000
    python run_studio.py --port 9000 --open

Open the page, then press **Start** for a real run or **Demo** to watch the whole
UI work with no API keys or ffmpeg.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser

from k100dra.web.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="K100DRA Studio web dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="Open the dashboard in a browser.")
    args = parser.parse_args()

    url = f"http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}"
    print(f"\n  🎬  K100DRA Studio → {url}\n")
    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
