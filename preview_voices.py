#!/usr/bin/env python3
import os

import soundfile as sf

from src.util import SR
from src.voice import VOICES, synth_phrase

TEXT = "ॐ नमः शिवाय। श्री राम जय राम जय जय राम।"


def main():
    os.makedirs("out", exist_ok=True)
    for voice, desc in VOICES.items():
        y = synth_phrase(TEXT, voice=voice, speed=0.85)
        path = os.path.join("out", f"voice_{voice}.wav")
        sf.write(path, y, SR)
        print(f"{voice:10s} {len(y) / SR:5.1f}s  {desc}  -> {path}")


if __name__ == "__main__":
    main()
