import argparse
import os
import subprocess
import sys

import normalize_audio


def run_main(extra_args=None):
    """Run main.py as a subprocess and return True if successful."""
    script_path = os.path.join(os.path.dirname(__file__), 'main.py')
    cmd = [sys.executable, script_path]
    if extra_args:
        cmd.extend(extra_args)
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"MAIN failed with exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Normalize audio then run main.py multiple times.'
    )
    parser.add_argument(
        '-n', '--number', type=int, default=10,
        help='Number of successful MAIN runs to execute (default: 10)'
    )
    parser.add_argument(
        'main_args', nargs=argparse.REMAINDER,
        help='Arguments to pass to main.py (use -- before these arguments)'
    )
    args = parser.parse_args()

    # Step 1: normalize audio
    normalize_audio.normalize_folder()

    success = 0
    attempts = 0
    while success < args.number:
        attempts += 1
        print(f"-- RUNNING MAIN ({attempts}) --")
        if run_main(args.main_args):
            success += 1
        else:
            print('MAIN errored, retrying...')

    print(f"Completed {success} successful runs after {attempts} attempts.")


if __name__ == '__main__':
    main()
