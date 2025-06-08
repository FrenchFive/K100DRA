import os
from pydub import AudioSegment

MUSIC_DIR = os.path.join(os.path.dirname(__file__), 'musics')
TARGET_DBFS = -20.0  # target volume in dBFS
TOLERANCE_DB = 1.0   # skip files already within this range


def match_target_amplitude(sound: AudioSegment, target_dBFS: float) -> AudioSegment:
    """Return a sound with the specified average volume."""
    change_in_dBFS = target_dBFS - sound.dBFS
    return sound.apply_gain(change_in_dBFS)


def normalize_folder(folder: str = MUSIC_DIR) -> None:
    """Normalize all audio files in the given folder in-place."""
    for fname in os.listdir(folder):
        if not fname.lower().endswith((
            '.mp3', '.wav', '.flac', '.ogg', '.m4a'
        )):
            continue

        path = os.path.join(folder, fname)
        try:
            audio = AudioSegment.from_file(path)
        except Exception as e:
            print(f"Skipping {fname}: {e}")
            continue

        # Skip if already close enough to target volume
        if abs(audio.dBFS - TARGET_DBFS) <= TOLERANCE_DB:
            print(f"{fname} within {TOLERANCE_DB} dB of target, skipping")
            continue

        normalized = match_target_amplitude(audio, TARGET_DBFS)
        normalized.export(path, format=fname.rsplit('.', 1)[-1])
        print(f"Normalized {fname} to {normalized.dBFS:.2f} dBFS")


if __name__ == '__main__':
    normalize_folder()
