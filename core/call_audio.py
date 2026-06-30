"""Захват звука созвона (Zoom, Meet, Teams) через WASAPI loopback Windows."""

import audioop
import struct
import threading
import time
from typing import Callable, Optional

import speech_recognition as sr

from config.settings import log, settings

STT_RATE = 16000
SAMPLE_WIDTH = 2  # int16

# Пороги для звука из колонок/наушников (loopback)
CALL_SILENCE_THRESHOLD = 350
CALL_SILENCE_SEC = 0.45
CALL_MIN_SPEECH_SEC = 0.7
CALL_MAX_SPEECH_SEC = 22.0
CALL_MIN_WORDS = 3


def _calc_level(pcm: bytes) -> float:
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"{count}h", pcm[: count * 2])
    return (sum(s * s for s in shorts) / count) ** 0.5


def _to_mono_16k(pcm: bytes, channels: int, sample_rate: int) -> bytes:
    """Конвертировать loopback PCM → mono 16 kHz для Google STT."""
    if channels == 2:
        pcm = audioop.tomono(pcm, SAMPLE_WIDTH, 0.5, 0.5)
        channels = 1
    if sample_rate != STT_RATE:
        pcm, _ = audioop.ratecv(pcm, SAMPLE_WIDTH, channels, sample_rate, STT_RATE, None)
    return pcm


def _recognize_pcm(pcm_16k: bytes, language_hint: str = "auto") -> Optional[str]:
    """Распознать речь (ru/en)."""
    if language_hint == "en":
        langs = ["en-US", "ru-RU"]
    elif language_hint == "ru":
        langs = ["ru-RU", "en-US"]
    else:
        langs = ["en-US", "ru-RU"]

    recognizer = sr.Recognizer()
    audio = sr.AudioData(pcm_16k, STT_RATE, SAMPLE_WIDTH)

    for lang in langs:
        try:
            text = recognizer.recognize_google(audio, language=lang)
            if text and text.strip():
                return text.strip()
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            log.warning("Call Google STT: %s", e)
            break

    # Fallback Vosk
    try:
        from core.vosk_stt import is_available, recognize_pcm
        if is_available():
            return recognize_pcm(pcm_16k, STT_RATE)
    except Exception as e:
        log.debug("call vosk: %s", e)
    return None


def _is_likely_question(text: str) -> bool:
    """Отфильтровать шум и короткие фразы."""
    words = text.split()
    if len(words) < CALL_MIN_WORDS:
        if "?" in text or text.lower().startswith(
            ("what", "why", "how", "tell", "describe", "can you", "could you",
             "расскаж", "опиш", "как", "что", "почему", "зачем", "назов")
        ):
            return True
        return False
    return True


def get_loopback_device() -> Optional[dict]:
    """Найти WASAPI loopback-устройство (звук из Zoom/Meet/Teams)."""
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        log.error("pyaudiowpatch не установлен — pip install pyaudiowpatch")
        return None

    p = pyaudio.PyAudio()
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

        if default_out.get("isLoopbackDevice"):
            return {
                "index": default_out["index"],
                "rate": int(default_out["defaultSampleRate"]),
                "channels": default_out["maxInputChannels"],
                "name": default_out["name"],
            }

        for loopback in p.get_loopback_device_info_generator():
            if default_out["name"] in loopback["name"]:
                return {
                    "index": loopback["index"],
                    "rate": int(loopback["defaultSampleRate"]),
                    "channels": loopback["maxInputChannels"],
                    "name": loopback["name"],
                }

        # Любое loopback
        for loopback in p.get_loopback_device_info_generator():
            return {
                "index": loopback["index"],
                "rate": int(loopback["defaultSampleRate"]),
                "channels": loopback["maxInputChannels"],
                "name": loopback["name"],
            }
    except Exception as e:
        log.error("get_loopback_device: %s", e)
    finally:
        p.terminate()
    return None


def test_call_audio() -> tuple[bool, str]:
    """Проверка доступности захвата звука созвона."""
    dev = get_loopback_device()
    if dev:
        return True, f"Захват созвона доступен: {dev['name']}"
    return False, (
        "WASAPI loopback недоступен. Установите: pip install pyaudiowpatch\n"
        "Используйте наушники — так JARVIS слышит только рекрутера."
    )


class CallAudioListener:
    """
    Непрерывно слушает звук созвона (WASAPI loopback).
    Zoom / Google Meet / Microsoft Teams / Discord — любой сервис,
    чей звук идёт в колонки или наушники.
    """

    def __init__(
        self,
        on_question: Callable[[str], None],
        on_level: Optional[Callable[[float], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        language_hint: str = "auto",
    ):
        self._on_question = on_question
        self._on_level = on_level
        self._on_status = on_status
        self._language_hint = language_hint
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_question = ""
        self._last_question_time = 0.0
        self._device: Optional[dict] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_language_hint(self, hint: str) -> None:
        self._language_hint = hint

    def start(self) -> tuple[bool, str]:
        """Запустить прослушивание созвона."""
        if self._running:
            return True, "Уже слушаю"

        self._device = get_loopback_device()
        if not self._device:
            return False, "Не удалось найти loopback-устройство"

        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        log.info("CallAudioListener: %s", self._device["name"])
        return True, f"Слушаю созвон: {self._device['name']}"

    def stop(self) -> None:
        self._running = False

    def _listen_loop(self) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            if self._on_status:
                self._on_status("Ошибка: pip install pyaudiowpatch")
            self._running = False
            return

        p = pyaudio.PyAudio()
        stream = None
        dev = self._device
        if not dev:
            self._running = False
            return

        rate = dev["rate"]
        channels = max(1, dev["channels"])
        chunk = 1024

        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=dev["index"],
                frames_per_buffer=chunk,
            )

            if self._on_status:
                self._on_status("live")

            frames: list[bytes] = []
            in_speech = False
            silence_start: Optional[float] = None
            speech_start: Optional[float] = None

            while self._running:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                except Exception as e:
                    log.debug("call read: %s", e)
                    continue

                level = _calc_level(data)
                if self._on_level:
                    self._on_level(level)

                now = time.time()

                if level >= CALL_SILENCE_THRESHOLD:
                    if not in_speech:
                        in_speech = True
                        speech_start = now
                        frames = []
                    silence_start = None
                    frames.append(data)

                    if speech_start and (now - speech_start) > CALL_MAX_SPEECH_SEC:
                        self._finalize_utterance(frames, rate, channels)
                        in_speech = False
                        frames = []
                        silence_start = None
                        speech_start = None
                else:
                    if in_speech:
                        frames.append(data)
                        if silence_start is None:
                            silence_start = now
                        elif now - silence_start >= CALL_SILENCE_SEC:
                            speech_dur = (now - (speech_start or now))
                            if speech_dur >= CALL_MIN_SPEECH_SEC:
                                self._finalize_utterance(frames, rate, channels)
                            in_speech = False
                            frames = []
                            silence_start = None
                            speech_start = None

        except Exception as e:
            log.error("call listen loop: %s", e)
            if self._on_status:
                self._on_status(f"Ошибка: {e}")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            p.terminate()
            self._running = False
            if self._on_status:
                self._on_status("idle")

    def _finalize_utterance(self, frames: list[bytes], rate: int, channels: int) -> None:
        """Распознать фразу и отправить как вопрос."""
        if not frames:
            return

        pcm = b"".join(frames)
        pcm_16k = _to_mono_16k(pcm, channels, rate)

        threading.Thread(
            target=self._recognize_and_emit,
            args=(pcm_16k,),
            daemon=True,
        ).start()

    def _recognize_and_emit(self, pcm_16k: bytes) -> None:
        text = _recognize_pcm(pcm_16k, self._language_hint)
        if not text:
            return
        if not _is_likely_question(text):
            log.debug("Пропуск короткой фразы: %s", text)
            return

        # Дедупликация
        norm = text.lower().strip()
        now = time.time()
        if norm == self._last_question and (now - self._last_question_time) < 45:
            return
        if self._last_question and norm in self._last_question and (now - self._last_question_time) < 20:
            return

        self._last_question = norm
        self._last_question_time = now
        log.info("Вопрос из созвона: %s", text[:100])
        self._on_question(text)
