#!/usr/bin/env python3
"""Normalize the music pool, then generate a batch of videos.

Kept for backwards compatibility — it simply normalizes ``musics/`` and then
calls the new ``main.py`` runner, which already retries failed runs internally.

    python batch_run.py          # normalize, then make 10 videos
    python batch_run.py -n 3     # ...make 3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import normalize_audio


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize audio then generate a batch.")
    parser.add_argument("-n", "--number", type=int, default=10, help="Number of videos (default: 10).")
    parser.add_argument("main_args", nargs=argparse.REMAINDER, help="Extra args passed to main.py.")
    args = parser.parse_args()

    normalize_audio.normalize_folder()

    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "main.py"), "-n", str(args.number)]
    cmd += [a for a in args.main_args if a != "--"]
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
