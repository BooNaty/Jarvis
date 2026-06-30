"""Режим собеседования: захват звука Zoom/Meet/Teams + быстрые подсказки."""

import threading
import queue
from typing import Callable, Optional

from config.settings import log, save_interview_entry
from core.brain import Brain
from core.call_audio import CallAudioListener, test_call_audio
from core.listener import Listener
from ui.interview_overlay import (
    STATE_IDLE,
    STATE_LISTENING,
    STATE_LIVE,
    STATE_THINKING,
    InterviewOverlay,
)
from ui.interview_setup import load_interview_profile, profile_to_context
from utils.lang_detect import resolve_interview_language


class InterviewMode:
    """
    Режим собеседования в два этапа:

    1. ПОДГОТОВКА — загрузить резюме, вакансию, профиль
    2. LIVE — скрытый режим: слушает звук созвона (WASAPI loopback)
       из Zoom / Google Meet / Teams / Discord и выдаёт ответы
       в невидимой панели (только для вас)
    """

    def __init__(
        self,
        brain: Brain,
        listener: Listener,
        overlay: Optional[InterviewOverlay] = None,
        on_enabled: Optional[Callable[[bool], None]] = None,
    ):
        self._brain = brain
        self._listener = listener
        self._overlay = overlay or InterviewOverlay()
        self._on_enabled = on_enabled
        self._active = False
        self._live = False
        self._busy = False
        self._lock = threading.Lock()
        self._call_listener: Optional[CallAudioListener] = None
        self._question_queue: queue.Queue[str] = queue.Queue()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def live(self) -> bool:
        return self._live

    @property
    def overlay(self) -> InterviewOverlay:
        return self._overlay

    def enable(self) -> bool:
        """Включить режим (подготовка)."""
        profile = load_interview_profile()
        if not profile.get("resume") and not profile.get("skills"):
            log.warning("Профиль собеседования пуст")

        self._active = True
        self._overlay.clear()
        self._overlay.show_panel()
        self._overlay.set_prep_mode(True)
        log.info("Режим собеседования: подготовка")

        if self._on_enabled:
            self._on_enabled(True)
        return True

    def disable(self) -> None:
        """Выключить полностью."""
        self.stop_live()
        self._active = False
        self._overlay.hide_panel()
        log.info("Режим собеседования выключен")
        if self._on_enabled:
            self._on_enabled(False)

    def toggle(self) -> bool:
        if self._active:
            self.disable()
            return False
        self.enable()
        return True

    def go_live(self) -> tuple[bool, str]:
        """
        СКРЫТЫЙ РЕЖИМ — начать слушать созвон.
        Захватывает звук из Zoom/Meet/Teams через WASAPI loopback.
        """
        if not self._active:
            return False, "Сначала включите режим собеседования"

        if self._live:
            return True, "Уже слушаю созвон"

        ok, msg = test_call_audio()
        if not ok:
            self._overlay.show_answer(msg)
            return False, msg

        profile = load_interview_profile()
        lang_hint = profile.get("interview_language", "auto")

        self._call_listener = CallAudioListener(
            on_question=self._on_call_question,
            on_level=self._overlay.set_audio_level if hasattr(self._overlay, 'set_audio_level') else None,
            on_status=self._on_call_status,
            language_hint=lang_hint,
        )

        started, start_msg = self._call_listener.start()
        if not started:
            return False, start_msg

        self._live = True
        self._overlay.set_prep_mode(False)
        self._overlay.set_state(STATE_LIVE)
        log.info("LIVE режим: слушаю созвон")
        return True, start_msg

    def stop_live(self) -> None:
        """Остановить прослушивание созвона."""
        if self._call_listener:
            self._call_listener.stop()
            self._call_listener = None
        self._live = False
        if self._active:
            self._overlay.set_state(STATE_IDLE)
            self._overlay.set_prep_mode(True)

    def toggle_live(self) -> tuple[bool, str]:
        if self._live:
            self.stop_live()
            return False, "Прослушивание созвона остановлено"
        return self.go_live()

    def _on_call_status(self, status: str) -> None:
        if status == "live":
            self._overlay.set_state(STATE_LIVE)
        elif status == "idle" and self._active:
            self._overlay.set_state(STATE_IDLE)

    def _on_call_question(self, question: str) -> None:
        """Автоматически: вопрос рекрутера из звука созвона."""
        if not self._live or not question.strip():
            return
        with self._lock:
            if self._busy:
                self._question_queue.put(question.strip())
                log.info("Вопрос в очереди: %s", question[:60])
                return
            self._busy = True
        threading.Thread(
            target=self._process_question,
            args=(question.strip(), True),
            daemon=True,
        ).start()

    def capture_question(self) -> None:
        """Ручной захват: микрофон (Ctrl+Shift+I)."""
        if not self._active:
            return
        with self._lock:
            if self._busy:
                return
            self._busy = True
        threading.Thread(target=self._process_voice_question, daemon=True).start()

    def process_text_question(self, question: str) -> None:
        if not self._active or not question.strip():
            return
        with self._lock:
            if self._busy:
                return
            self._busy = True
        threading.Thread(
            target=self._process_question,
            args=(question.strip(), False),
            daemon=True,
        ).start()

    def _process_voice_question(self) -> None:
        try:
            profile = load_interview_profile()
            lang_hint = profile.get("interview_language", "auto")
            self._overlay.set_state(STATE_LISTENING)
            question = self._listener.listen_interview_question(lang_hint)
            if not question:
                self._overlay.show_answer(
                    "Не распознано. Используйте Ctrl+Shift+L для звука созвона\n"
                    "или Ctrl+Shift+V для текста из буфера."
                )
                self._overlay.set_state(STATE_LIVE if self._live else STATE_IDLE)
                return
            self._process_question(question, from_call=False)
        except Exception as e:
            log.error("capture_question: %s", e)
            self._overlay.show_answer(f"Ошибка: {e}")
            self._overlay.set_state(STATE_LIVE if self._live else STATE_IDLE)
        finally:
            with self._lock:
                self._busy = False

    def _process_question(self, question: str, from_call: bool = False) -> None:
        try:
            self._overlay.show_question(question)
            self._overlay.set_state(STATE_THINKING)

            profile = load_interview_profile()
            profile_lang = profile.get("interview_language", "auto")
            answer_lang = resolve_interview_language(question, profile_lang)

            self._overlay.set_answer_language(answer_lang)
            self._overlay.start_streaming_answer()

            context = profile_to_context(profile)
            if from_call:
                context += (
                    "\n\n[Источник: живой звук видеозвонка Zoom/Meet/Teams. "
                    "В транскрипте может быть речь рекрутера и кандидата. "
                    "Ответь на последний вопрос интервьюера.]"
                )

            def on_chunk(text: str) -> None:
                self._overlay.append_answer_chunk(text)

            self._brain.interview_answer_stream(
                question=question,
                context=context,
                language=answer_lang,
                style=profile.get("answer_style", "concise"),
                on_chunk=on_chunk,
            )

            full_answer = self._overlay.get_answer_text()
            save_interview_entry(question, full_answer, answer_lang, from_call)

            self._overlay.finish_streaming()
            if self._live:
                self._overlay.set_state(STATE_LIVE)
            log.info("Interview [%s%s]: %s",
                     answer_lang, " call" if from_call else "", question[:80])

        except Exception as e:
            log.error("process_question: %s", e)
            self._overlay.show_answer(f"Ошибка: {e}")
            self._overlay.set_state(STATE_LIVE if self._live else STATE_IDLE)
        finally:
            with self._lock:
                self._busy = False
            self._process_next_queued()

    def _process_next_queued(self) -> None:
        """Обработать следующий вопрос из очереди."""
        try:
            next_q = self._question_queue.get_nowait()
        except queue.Empty:
            return
        with self._lock:
            if self._busy:
                self._question_queue.put(next_q)
                return
            self._busy = True
        threading.Thread(
            target=self._process_question,
            args=(next_q, True),
            daemon=True,
        ).start()
