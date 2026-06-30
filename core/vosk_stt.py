"""Офлайн STT через Vosk: быстрая модель для wake word, большая — для команд."""

import json
import threading
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR, log

_vosk_wake_model = None
_vosk_command_model = None
_vosk_command_loading = False
_vosk_available: bool | None = None

# Wake word — только лёгкая модель (грузится за ~1 с)
WAKE_MODEL_CANDIDATES = [
    BASE_DIR / "models" / "vosk-model-small-ru-0.22",
    BASE_DIR.parent / "jarvis_assistant" / "vosk-model-small-ru-0.22",
]

# Команды — лучшее качество (грузится долго, в фоне)
COMMAND_MODEL_CANDIDATES = [
    BASE_DIR / "models" / "vosk-model-ru-0.42",
    BASE_DIR / "models" / "vosk-model-small-ru-0.22",
    BASE_DIR.parent / "jarvis_assistant" / "vosk-model-small-ru-0.22",
]


def _valid_model(path: Path) -> bool:
    return path.exists() and (path / "am" / "final.mdl").exists()


def _find_wake_model() -> Optional[Path]:
    for p in WAKE_MODEL_CANDIDATES:
        if _valid_model(p):
            return p
    return None


def _find_command_model() -> Optional[Path]:
    for p in COMMAND_MODEL_CANDIDATES:
        if _valid_model(p):
            return p
    return None


def is_available() -> bool:
    global _vosk_available
    if _vosk_available is not None:
        return _vosk_available
    try:
        import vosk  # noqa: F401
        _vosk_available = _find_wake_model() is not None
    except ImportError:
        _vosk_available = False
    return _vosk_available


def get_wake_model_path() -> Optional[str]:
    m = _find_wake_model()
    return str(m) if m else None


def get_model_path() -> Optional[str]:
    m = _find_command_model()
    return str(m) if m else None


def _load_model(path: str, label: str):
    from vosk import Model, SetLogLevel

    SetLogLevel(-1)
    log.info("Загрузка Vosk (%s): %s", label, path)
    return Model(path)


def get_wake_model():
    """Быстрая модель для wake word «Джарвис»."""
    global _vosk_wake_model

    if not is_available():
        return None

    if _vosk_wake_model is None:
        path = get_wake_model_path()
        if not path:
            return None
        _vosk_wake_model = _load_model(path, "wake")

    return _vosk_wake_model


def get_model():
    """Модель для команд: большая, если уже загружена, иначе быстрая."""
    if _vosk_command_model is not None:
        return _vosk_command_model
    return get_wake_model()


def preload_command_model() -> None:
    """Фоновая загрузка большой STT-модели (~2 мин)."""
    global _vosk_command_loading, _vosk_command_model

    if _vosk_command_model is not None or _vosk_command_loading:
        return

    path = get_model_path()
    wake_path = get_wake_model_path()
    if not path or path == wake_path:
        return

    _vosk_command_loading = True

    def _load() -> None:
        global _vosk_command_model, _vosk_command_loading
        try:
            _vosk_command_model = _load_model(path, "команды")
            log.info("STT-модель команд готова")
        except Exception as e:
            log.error("Ошибка загрузки STT-модели: %s", e)
        finally:
            _vosk_command_loading = False

    threading.Thread(target=_load, daemon=True, name="vosk-preload").start()


def _recognize_with_model(model, pcm_16k_mono: bytes, sample_rate: int, log_label: str) -> Optional[str]:
    if model is None:
        return None

    try:
        from vosk import KaldiRecognizer

        rec = KaldiRecognizer(model, sample_rate)
        step = 8000
        for i in range(0, len(pcm_16k_mono), step):
            rec.AcceptWaveform(pcm_16k_mono[i : i + step])
        result = json.loads(rec.FinalResult())
        text = result.get("text", "").strip()
        if text:
            log.info("Vosk (%s): %s", log_label, text)
            return text
    except Exception as e:
        log.error("Vosk STT (%s): %s", log_label, e)
    return None


def recognize_pcm_wake(pcm_16k_mono: bytes, sample_rate: int = 16000) -> Optional[str]:
    """Распознать короткую фразу wake word."""
    return _recognize_with_model(get_wake_model(), pcm_16k_mono, sample_rate, "wake")


def recognize_pcm(pcm_16k_mono: bytes, sample_rate: int = 16000) -> Optional[str]:
    """Распознать команду (большая модель, если готова)."""
    model = _vosk_command_model or get_wake_model()
    label = "команды" if model is _vosk_command_model else "wake"
    return _recognize_with_model(model, pcm_16k_mono, sample_rate, label)
