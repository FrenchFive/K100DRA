import os
from pydub import AudioSegment

MUSIC_DIR = os.path.join(os.path.dirname(__file__), 'musics')
TARGET_DBFS = -20.0  # target volume in dBFS


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

        normalized = match_target_amplitude(audio, TARGET_DBFS)
        normalized.export(path, format=fname.rsplit('.', 1)[-1])
        print(f"Normalized {fname}")


if __name__ == '__main__':
    normalize_folder()
