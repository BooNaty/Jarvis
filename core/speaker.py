"""Синтез речи: взрослый мужской вежливый голос (ru-RU-DmitryNeural)."""

import asyncio
import hashlib
import queue
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import edge_tts
import pygame

from config.settings import CACHE_DIR, SOUNDS_DIR, log, settings

# Кешированные фразы — тон дворецкого, на «Вы»
CACHED_PHRASES = {
    "listening": "Слушаю Вас, {title}.",
    "executing": "Сейчас выполню, {title}.",
    "done": "Готово, {title}.",
    "not_understood": "Прошу прощения, {title}, я не разобрал команду.",
    "confirm": "Разрешите подтвердить: скажите «да», {title}.",
    "cancelled": "Как скажете, {title}. Команда отменена.",
    "error": "Прошу прощения, {title}. Произошла ошибка. {detail}",
    "greeting": "Добрый день, {title}. JARVIS к Вашим услугам.",
    "welcome": "Все системы в норме, {title}. JARVIS готов к работе.",
    "at_service": "Всегда к Вашим услугам, {title}.",
}


def polish_speech(text: str, title: str | None = None) -> str:
    """
    Подготовить динамический текст для TTS:
    уважительный тон, без лишних символов.
    """
    if not text:
        return text
    t = title or settings.user_title
    # Убрать markdown и эмодзи
    t_text = re.sub(r"[*#`_]", "", text)
    t_text = re.sub(r"[\U00010000-\U0010ffff]", "", t_text)
    t_text = t_text.strip()
    # Если нет обращения — мягко добавить в конец коротких фраз
    if t.lower() not in t_text.lower() and len(t_text) < 120:
        if not t_text.endswith((".", "!", "?")):
            t_text += "."
    return t_text


class Speaker:
    """TTS: edge-tts + pygame. Не блокирует UI и wake word."""

    def __init__(self, on_speaking: Optional[Callable[[bool], None]] = None):
        self._on_speaking = on_speaking
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._process_queue, daemon=True)
        self._speaking = False
        self._stop_event = threading.Event()
        self._title = settings.user_title

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=24000)

        self._worker.start()
        threading.Thread(target=self._pregenerate_cache, daemon=True).start()

    def set_title(self, title: str) -> None:
        self._title = title
        # Перегенерировать кеш с новым обращением в фоне
        threading.Thread(target=self._pregenerate_cache, daemon=True).start()

    def _format(self, text: str) -> str:
        return text.format(title=self._title)

    def say(self, text: str, block: bool = False) -> None:
        if not text:
            return
        text = polish_speech(text, self._title)
        if block:
            self._speak_sync(text)
        else:
            self._queue.put(text)

    def say_cached(self, key: str, **kwargs) -> None:
        template = CACHED_PHRASES.get(key, "")
        text = template.format(title=self._title, detail=kwargs.get("detail", ""), **kwargs)
        self.say(text)

    def play_sound(self, name: str) -> None:
        path = SOUNDS_DIR / f"{name}.wav"
        if path.exists():
            threading.Thread(target=self._play_file, args=(path,), daemon=True).start()

    def is_speaking(self) -> bool:
        return self._speaking

    def stop(self) -> None:
        self._stop_event.set()
        pygame.mixer.music.stop()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _set_speaking(self, state: bool) -> None:
        self._speaking = state
        if self._on_speaking:
            self._on_speaking(state)

    def _process_queue(self) -> None:
        while True:
            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._speak_sync(text)

    def _speak_sync(self, text: str) -> None:
        self._stop_event.clear()
        self._set_speaking(True)
        try:
            self._play_file(self._get_audio_path(text))
        except Exception as e:
            log.error("Ошибка TTS: %s", e)
        finally:
            self._set_speaking(False)

    def _cache_key(self, text: str) -> str:
        payload = f"{settings.tts_voice}|{settings.tts_rate}|{settings.tts_pitch}|{text}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def _get_audio_path(self, text: str) -> Path:
        key = self._cache_key(text)
        path = CACHE_DIR / f"{key}.mp3"
        if not path.exists():
            asyncio.run(self._generate_tts(text, path))
        return path

    async def _generate_tts(self, text: str, path: Path) -> None:
        communicate = edge_tts.Communicate(
            text,
            settings.tts_voice,
            rate=settings.tts_rate,
            pitch=settings.tts_pitch,
            volume=settings.tts_volume,
        )
        await communicate.save(str(path))

    def _play_file(self, path: Path) -> None:
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                time.sleep(0.05)
            pygame.mixer.music.stop()
        except Exception as e:
            log.error("Ошибка воспроизведения %s: %s", path, e)

    def _pregenerate_cache(self) -> None:
        for key in CACHED_PHRASES:
            try:
                text = self._format(
                    CACHED_PHRASES[key].replace("{detail}", "повторите позже")
                )
                self._get_audio_path(text)
            except Exception as e:
                log.debug("Кеш фразы %s: %s", key, e)

    def wait_until_done(self, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        while (self._speaking or not self._queue.empty()) and time.time() < deadline:
            time.sleep(0.1)
