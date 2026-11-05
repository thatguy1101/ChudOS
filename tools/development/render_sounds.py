#!/usr/bin/env python3
"""Generate the ChudOS decorative sounds (original: two short sine tones with a fade). Stdlib only."""
import math
import struct
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "branding" / "sounds"
RATE = 44100


def tone(freq, ms, amp=0.35):
    n = int(RATE * ms / 1000)
    return [amp * math.sin(2 * math.pi * freq * i / RATE) * min(1, i / 400, (n - i) / 1200) for i in range(n)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    samples = tone(660, 90) + tone(880, 140)
    with wave.open(str(OUT / "profile-applied.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))
    print("wrote", OUT / "profile-applied.wav")


if __name__ == "__main__":
    main()
