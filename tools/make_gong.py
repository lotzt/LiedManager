"""Erzeugt ui/assets/gong.wav: ein selbst berechneter Gong (keine fremden Aufnahmen, keine Lizenzfragen).

Aufruf:  python tools/make_gong.py   (nur nötig, wenn der Klang geändert werden soll; die Datei liegt im Repository)
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
SECONDS = 7.0
OUT = Path(__file__).resolve().parent.parent / "ui" / "assets" / "gong.wav"

# (Frequenz in Hz, Lautstärke, Abklingzeit in s): ein Tam-Tam hat unharmonische Obertöne, die leicht gegeneinander schweben
PARTIALS = [
    (92.0, 1.00, 4.2), (92.9, 0.55, 3.8), (141.0, 0.60, 3.4), (187.0, 0.45, 3.0), (231.0, 0.40, 2.8),
    (279.0, 0.34, 2.4), (352.0, 0.26, 2.0), (417.0, 0.22, 1.8), (533.0, 0.16, 1.4), (689.0, 0.12, 1.1),
    (864.0, 0.08, 0.9), (1130.0, 0.05, 0.7),
]


def main() -> None:
    random.seed(7)
    total = int(RATE * SECONDS)
    samples = []
    for n in range(total):
        t = n / RATE
        value = 0.0
        for freq, amp, decay in PARTIALS:
            wobble = 1.0 + 0.0025 * math.sin(2 * math.pi * 0.35 * t + freq)       # leichtes Schweben
            value += amp * math.exp(-t / decay) * math.sin(2 * math.pi * freq * wobble * t)
        value += 0.5 * (random.random() * 2 - 1) * math.exp(-t / 0.06)             # Anschlag
        value *= min(1.0, t / 0.004)                                                  # kurzer Einschwingvorgang
        value *= min(1.0, (SECONDS - t) / 0.8)                                        # sanftes Ausklingen am Ende
        samples.append(value)
    peak = max(abs(v) for v in samples) or 1.0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b"".join(struct.pack("<h", int(v / peak * 0.85 * 32767)) for v in samples))
    print(f"{OUT} geschrieben ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
