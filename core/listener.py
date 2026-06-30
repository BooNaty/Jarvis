"""Wake word (Vosk офлайн) + распознавание речи (Google STT / Vosk fallback)."""

import struct
import re
import threading
import time
from typing import Callable, Optional

from rapidfuzz import fuzz

try:
    import pyaudio
except ImportError:
    import pyaudiowpatch as pyaudio
import speech_recognition as sr

from config.settings import SOUNDS_DIR, log, settings

# Порог тишины для остановки записи
SILENCE_THRESHOLD = settings.silence_threshold
SILENCE_DURATION = settings.silence_duration
MAX_RECORD_SECONDS = settings.max_record_seconds
SAMPLE_RATE = 16000
CHUNK = 512

# Wake word: только явная активация (без ложных срабатываний)
WAKE_SILENCE_THRESHOLD = 280
WAKE_SILENCE_DURATION = 1.1
WAKE_MAX_PHRASE = 4.5
WAKE_COOLDOWN = 3.5
WAKE_MIN_PHRASE_CHARS = 5
WAKE_WORDS = ("джарвис", "jarvis", "жарвис", "джерри", "дарвис", "гарвис")
WAKE_FUZZY_TARGETS = ("джарвис", "jarvis", "жарвис")
WAKE_FUZZY_MIN_SCORE = 82
WAKE_PARTIAL_MIN_SCORE = 90


class Listener:
    """Слушает wake word 24/7, затем записывает команду."""

    def __init__(
        self,
        on_wake: Optional[Callable[[], None]] = None,
        on_audio_level: Optional[Callable[[float], None]] = None,
        on_listening: Optional[Callable[[bool], None]] = None,
    ):
        self._on_wake = on_wake
        self._on_audio_level = on_audio_level
        self._on_listening = on_listening
        self._paused = False
        self._active = False
        self._audio: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._thread: Optional[threading.Thread] = None
        self._recognizer = sr.Recognizer()
        self._recognizer.dynamic_energy_threshold = True
        self._recognizer.energy_threshold = 300
        self._vosk_model = None
        self._pending_command_hint: Optional[str] = None

    def consume_command_hint(self) -> Optional[str]:
        """Команда из той же фразы, что и wake word («Джарвис, открой Steam»)."""
        hint = self._pending_command_hint
        self._pending_command_hint = None
        return hint

    def start(self) -> None:
        """Запустить фоновый поток wake word."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._wake_loop, daemon=True)
        self._thread.start()
        log.info("Listener запущен, wake word: «джарвис» (офлайн Vosk)")

    def stop(self) -> None:
        """Остановить слушатель."""
        self._active = False
        self._cleanup()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def trigger_manual(self) -> None:
        """Ручная активация (Ctrl+J) — имитация wake word."""
        if not self._paused:
            self._handle_wake()

    def listen_command(self) -> Optional[str]:
        """Записать и распознать команду после wake word."""
        self._set_listening(True)
        try:
            audio_data = self._record_until_silence()
            if not audio_data:
                return None
            text = self._recognize(audio_data)
            if text:
                text = self._strip_wake_from_command(text)
            return text or None
        finally:
            self._set_listening(False)

    def listen_interview_question(self, language_hint: str = "auto") -> Optional[str]:
        """Быстрая запись вопроса для режима собеседования."""
        self._set_listening(True)
        try:
            audio_data = self._record_until_silence(
                max_seconds=settings.interview_max_record,
                silence_duration=settings.interview_silence_duration,
            )
            if not audio_data:
                return None
            return self._recognize_bilingual(audio_data, language_hint)
        finally:
            self._set_listening(False)

    def listen_confirmation(self, timeout: float = 5.0) -> bool:
        """Слушать подтверждение «да» в течение timeout секунд."""
        self._set_listening(True)
        try:
            audio_data = self._record_until_silence(max_seconds=timeout)
            if not audio_data:
                return False
            text = self._recognize(audio_data)
            if text:
                text_lower = text.lower().strip()
                return text_lower in ("да", "yes", "подтверждаю", "верно", "ага", "конечно")
            return False
        finally:
            self._set_listening(False)

    def _init_vosk_wake(self) -> bool:
        """Загрузить быструю Vosk-модель для wake word."""
        from core.vosk_stt import get_wake_model, is_available

        if not is_available():
            log.warning(
                "Vosk-модель не найдена — wake word отключён, используйте Ctrl+J. "
                "Положите vosk-model-small-ru-0.22 в models/ или jarvis_assistant/"
            )
            return False

        log.info("Загрузка wake-модели...")
        self._vosk_model = get_wake_model()
        if self._vosk_model:
            log.info("Wake word готов")
        return self._vosk_model is not None

    def _wake_words(self) -> tuple[str, ...]:
        extra = settings.wake_word.lower().strip()
        if extra and extra not in WAKE_WORDS:
            return WAKE_WORDS + (extra,)
        return WAKE_WORDS

    def _word_is_wake(self, word: str) -> bool:
        clean = word.lower().strip(".,!?")
        if len(clean) < 4:
            return False
        if clean in self._wake_words():
            return True
        return any(
            fuzz.ratio(clean, target) >= WAKE_FUZZY_MIN_SCORE
            for target in WAKE_FUZZY_TARGETS
        )

    def _wake_token_in_text(self, wake: str, text: str) -> bool:
        """Wake-слово как отдельное слово, не подстрока."""
        lower = text.lower()
        wake = wake.lower()
        start = 0
        while True:
            idx = lower.find(wake, start)
            if idx < 0:
                return False
            before = lower[idx - 1] if idx > 0 else " "
            after = lower[idx + len(wake)] if idx + len(wake) < len(lower) else " "
            if not before.isalnum() and not after.isalnum():
                return True
            start = idx + 1

    def _contains_wake_word(self, text: str) -> bool:
        lowered = text.lower().strip()
        if len(lowered) < WAKE_MIN_PHRASE_CHARS:
            return False
        words = lowered.split()
        if len(words) > 8:
            return False
        for w in self._wake_words():
            if len(w) >= 5 and self._wake_token_in_text(w, lowered):
                return True
        if any(self._word_is_wake(w) for w in words):
            return True
        return (
            fuzz.partial_ratio("джарвис", lowered) >= WAKE_PARTIAL_MIN_SCORE
            or fuzz.partial_ratio("jarvis", lowered) >= WAKE_PARTIAL_MIN_SCORE
        )

    def _extract_command_after_wake(self, text: str) -> Optional[str]:
        """«Джарвис открой Steam» → «открой Steam»."""
        words = text.split()
        for i, word in enumerate(words):
            if self._word_is_wake(word):
                rest = " ".join(words[i + 1 :]).strip(" ,.")
                if rest:
                    return rest
        lower = text.lower()
        for w in sorted(self._wake_words(), key=len, reverse=True):
            idx = lower.find(w)
            if idx >= 0:
                rest = text[idx + len(w) :].strip(" ,.")
                if rest:
                    return rest
        return None

    def _strip_wake_from_command(self, text: str) -> str:
        """Убрать «джарвис» из начала команды: «джарвис открой стим» → «открой стим»."""
        result = text.strip()
        lower = result.lower()
        for w in self._wake_words():
            if lower.startswith(w):
                result = result[len(w) :].lstrip(" ,.")
                break
        return result.strip() or text.strip()

    def _pick_best_transcript(self, *candidates: Optional[str]) -> Optional[str]:
        """Выбрать лучший вариант из Google / Vosk."""
        cleaned = [c.strip() for c in candidates if c and c.strip()]
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return cleaned[0]

        # Если один вариант совпадает с известным приложением — предпочитаем его
        for text in cleaned:
            from core.local_intent import _resolve_app_name

            if _resolve_app_name(text):
                return text

        # Иначе предпочитаем Google (обычно первый после фильтра)
        for text in cleaned:
            if re.search(r"[a-zA-Z]", text):
                return text
        return max(cleaned, key=len)

    def _open_input_stream(self, audio: pyaudio.PyAudio):
        """Открыть микрофон с логом устройства."""
        try:
            default = audio.get_default_input_device_info()
            log.info(
                "Микрофон: [%s] %s",
                default.get("index"),
                default.get("name"),
            )
        except Exception as e:
            log.warning("Не удалось определить микрофон по умолчанию: %s", e)

        return audio.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=CHUNK,
        )

    def _wake_loop(self) -> None:
        """Фон: микрофон → короткие фразы → Vosk → «джарвис»."""
        if not self._init_vosk_wake():
            self._active = True
            while self._active:
                time.sleep(0.5)
            return

        self._active = True
        while self._active:
            try:
                self._run_wake_session()
            except Exception as e:
                log.error("Ошибка wake loop: %s", e)
            finally:
                self._cleanup()

            if self._active:
                log.warning("Перезапуск прослушивания микрофона через 2 сек...")
                time.sleep(2.0)

    def _run_wake_session(self) -> None:
        """Одна сессия прослушивания (перезапускается при сбое)."""
        self._audio = pyaudio.PyAudio()
        self._stream = self._open_input_stream(self._audio)
        log.info("Офлайн wake word: слушаю микрофон (скажите «Джарвис» или Ctrl+J)...")

        while self._active:
            if self._paused:
                time.sleep(0.1)
                continue

            phrase = self._capture_wake_phrase()
            if not phrase:
                continue

            text = self._recognize_wake_phrase(phrase)
            if text:
                log.debug("Wake фраза: %s", text)
            if text and self._contains_wake_word(text):
                hint = self._extract_command_after_wake(text)
                if hint and len(hint.strip()) < 4:
                    hint = None
                log.info("Wake word обнаружен: %s", text)
                if hint:
                    log.info("Команда в той же фразе: %s", hint)
                self._handle_wake(hint)
                time.sleep(WAKE_COOLDOWN)
            elif text and len(text.strip()) >= 4:
                log.debug("Фоновый шум / не wake: %s", text)

    def _capture_wake_phrase(self) -> Optional[bytes]:
        """Записать короткую фразу при появлении речи (VAD)."""
        if not self._stream:
            return None

        frames: list[bytes] = []
        speech_started = False
        silence_start: Optional[float] = None
        started = time.time()

        while time.time() - started < WAKE_MAX_PHRASE:
            pcm = self._stream.read(CHUNK, exception_on_overflow=False)
            level = self._calc_level(pcm)

            if self._on_audio_level:
                self._on_audio_level(level)

            if level >= WAKE_SILENCE_THRESHOLD:
                speech_started = True
                frames.append(pcm)
                silence_start = None
            elif speech_started:
                frames.append(pcm)
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= WAKE_SILENCE_DURATION:
                    break
            else:
                # Тишина до начала речи — не копим буфер
                time.sleep(0.01)

        if not frames:
            return None
        return b"".join(frames)

    def _recognize_wake_phrase(self, pcm_data: bytes) -> Optional[str]:
        """Офлайн распознавание короткой фразы (быстрая модель)."""
        from core.vosk_stt import recognize_pcm_wake

        text = recognize_pcm_wake(pcm_data, SAMPLE_RATE)
        if text:
            log.debug("Wake Vosk: %s", text)
        return text

    def _handle_wake(self, command_hint: Optional[str] = None) -> None:
        self._pending_command_hint = command_hint
        if self._on_wake:
            self._on_wake()

    def _record_until_silence(
        self,
        max_seconds: float = MAX_RECORD_SECONDS,
        silence_duration: float | None = None,
    ) -> Optional[bytes]:
        """Запись с микрофона до тишины."""
        silence_dur = silence_duration if silence_duration is not None else SILENCE_DURATION
        min_record = getattr(settings, "min_record_seconds", 1.0)
        audio = pyaudio.PyAudio()
        frames: list[bytes] = []
        silence_start: Optional[float] = None
        started = time.time()
        speech_seen = False

        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )

            while time.time() - started < max_seconds:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)

                level = self._calc_level(data)
                if self._on_audio_level:
                    self._on_audio_level(level)

                if level >= SILENCE_THRESHOLD:
                    speech_seen = True
                    silence_start = None
                elif speech_seen and time.time() - started >= min_record:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= silence_dur:
                        break

            stream.stop_stream()
            stream.close()
        except Exception as e:
            log.error("Ошибка записи: %s", e)
            return None
        finally:
            audio.terminate()

        if not frames:
            return None
        return b"".join(frames)

    def _recognize_bilingual(self, pcm_data: bytes, language_hint: str = "auto") -> Optional[str]:
        """Распознавание: Google STT → fallback Vosk."""
        if language_hint == "en":
            langs = ["en-US", "ru-RU"]
        elif language_hint == "ru":
            langs = ["ru-RU", "en-US"]
        else:
            langs = ["en-US", "ru-RU"]

        audio = sr.AudioData(pcm_data, SAMPLE_RATE, 2)
        for lang in langs:
            try:
                text = self._recognizer.recognize_google(audio, language=lang)
                if text and text.strip():
                    log.info("Распознано Google (%s): %s", lang, text)
                    return text.strip()
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                log.warning("Google STT недоступен: %s", e)
                break
            except Exception as e:
                log.error("recognize_bilingual: %s", e)
                break

        # Fallback: Vosk офлайн
        return self._recognize_vosk(pcm_data)

    def _recognize_vosk(self, pcm_data: bytes) -> Optional[str]:
        from core.vosk_stt import is_available, recognize_pcm
        if not is_available():
            return None
        text = recognize_pcm(pcm_data, SAMPLE_RATE)
        return text

    def _recognize(self, pcm_data: bytes) -> Optional[str]:
        """Google STT + Vosk — берём лучший результат."""
        vosk_text = self._recognize_vosk(pcm_data)
        google_text: Optional[str] = None

        try:
            audio = sr.AudioData(pcm_data, SAMPLE_RATE, 2)
            google_text = self._recognizer.recognize_google(
                audio, language=settings.stt_language
            )
            if google_text:
                google_text = google_text.strip()
                log.info("Распознано Google: %s", google_text)
        except sr.UnknownValueError:
            log.warning("Google: речь не распознана, пробую Vosk")
        except sr.RequestError as e:
            log.warning("Google STT недоступен (%s), пробую Vosk", e)
        except Exception as e:
            log.error("Ошибка Google STT: %s", e)

        best = self._pick_best_transcript(google_text, vosk_text)
        if best:
            log.info("Итог STT: %s", best)
        return best

    @staticmethod
    def _calc_level(pcm: bytes) -> float:
        """Вычислить уровень громкости из PCM."""
        count = len(pcm) // 2
        if count == 0:
            return 0.0
        fmt = f"{count}h"
        shorts = struct.unpack(fmt, pcm[: count * 2])
        sum_squares = sum(s * s for s in shorts)
        rms = (sum_squares / count) ** 0.5
        return rms

    def _set_listening(self, state: bool) -> None:
        if self._on_listening:
            self._on_listening(state)

    def _cleanup(self) -> None:
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        if self._audio:
            try:
                self._audio.terminate()
            except Exception:
                pass

    @staticmethod
    def test_microphone() -> tuple[bool, str]:
        """Тест микрофона для мастера настройки."""
        try:
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            data = stream.read(CHUNK, exception_on_overflow=False)
            stream.close()
            audio.terminate()
            level = Listener._calc_level(data)
            if level > 50:
                return True, f"Микрофон работает (уровень: {int(level)})"
            return True, "Микрофон обнаружен, но сигнал слабый — проверьте громкость"
        except Exception as e:
            return False, f"Ошибка микрофона: {e}"
