"""Генерация ресурсов: иконка и звуки активации."""

import math
import struct
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
ASSETS = BASE / "assets"
SOUNDS = ASSETS / "sounds"


def generate_icon() -> None:
    """Создать jarvis.ico."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Градиентный круг
    cx, cy = size // 2, size // 2
    for r in range(size // 2, 0, -1):
        t = r / (size // 2)
        color = (
            int(0 + 20 * t),
            int(120 + 60 * t),
            int(200 + 55 * t),
            255,
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Буква J
    try:
        font = ImageFont.truetype("arial.ttf", 120)
    except OSError:
        font = ImageFont.load_default()
    draw.text((cx, cy), "J", fill=(255, 255, 255, 255), font=font, anchor="mm")

    ASSETS.mkdir(parents=True, exist_ok=True)
    img.save(ASSETS / "jarvis.ico", format="ICO", sizes=[(256, 256), (64, 64), (32, 32), (16, 16)])
    print(f"Иконка: {ASSETS / 'jarvis.ico'}")


def generate_tone(path: Path, freq: float, duration: float, fade: bool = True) -> None:
    """Сгенерировать WAV-тон."""
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    amplitude = 8000

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        for i in range(n_samples):
            t = i / sample_rate
            env = 1.0
            if fade:
                fade_len = int(sample_rate * 0.02)
                if i < fade_len:
                    env = i / fade_len
                elif i > n_samples - fade_len:
                    env = (n_samples - i) / fade_len
            val = int(amplitude * env * math.sin(2 * math.pi * freq * t))
            wf.writeframes(struct.pack("<h", val))


def generate_sounds() -> None:
    """Создать activate.wav и deactivate.wav."""
    SOUNDS.mkdir(parents=True, exist_ok=True)
    generate_tone(SOUNDS / "activate.wav", 880, 0.15)
    generate_tone(SOUNDS / "deactivate.wav", 440, 0.12)
    print(f"Звуки: {SOUNDS}")


if __name__ == "__main__":
    generate_icon()
    generate_sounds()
    print("Ресурсы созданы.")
