"""Оркестратор: связывает listener, brain, speaker, router и UI."""

import threading
import time
from enum import Enum
from typing import Optional

import keyboard
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QSystemTrayIcon

from config.settings import INTERVIEW_DISCLAIMER_FLAG, log, settings
from core.brain import Brain, CodingResult
from core.command_router import CommandRouter
from core.interview_mode import InterviewMode
from core.listener import Listener
from core.speaker import Speaker
from skills import app_launcher, extras
from skills.system_indexer import scan_all
from ui.overlay import (
    STATE_LISTENING,
    STATE_SLEEPING,
    STATE_SPEAKING,
    STATE_THINKING,
    OverlayWindow,
)
from ui.tray import JarvisTray


class AssistantState(Enum):
    SLEEPING = "sleeping"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CONFIRMING = "confirming"


class Assistant:
    """Главный класс — управляет всеми компонентами."""

    def __init__(self, minimized: bool = False):
        self._minimized = minimized
        self._state = AssistantState.SLEEPING
        self._lock = threading.Lock()
        self._processing = False

        # UI
        self.overlay = OverlayWindow()
        self.tray = JarvisTray()

        # Ядро
        self.speaker = Speaker(on_speaking=self._on_speaking)
        self.brain = Brain()
        self.listener = Listener(
            on_wake=self._on_wake,
            on_audio_level=self._on_audio_level,
            on_listening=self._on_listening_flag,
        )
        self.router = CommandRouter(
            brain=self.brain,
            on_code=self._on_code_result,
            on_timer=lambda text: self.speaker.say(
                f"Напоминание, {settings.user_title}: {text}"
            ),
        )
        self.interview = InterviewMode(
            brain=self.brain,
            listener=self.listener,
            on_enabled=self._on_interview_mode_changed,
        )

        self.brain.set_title(settings.user_title)
        self.speaker.set_title(settings.user_title)
        self._setup_hotkey()
        self._setup_interview_hotkeys()

        # Полное сканирование ПК в фоне
        threading.Thread(target=self._background_scan, daemon=True).start()
        threading.Thread(target=app_launcher.discover_apps, daemon=True).start()

    def start(self) -> None:
        """Запуск ассистента."""
        log.info("JARVIS запускается...")
        from core.llm_provider import log_provider_status
        from core.local_intent import refresh_from_index
        from core.vosk_stt import preload_command_model
        from skills.system_indexer import load_index

        load_index()
        refresh_from_index()
        log_provider_status()
        preload_command_model()
        self._wire_signals()
        self.tray.show()
        self.listener.start()

        if self._minimized:
            self.overlay.hide_overlay()
        else:
            self.overlay.show_overlay()

        self._set_state(AssistantState.SLEEPING)
        if not self._minimized:
            self.speaker.say_cached("greeting")

    def stop(self) -> None:
        """Остановка."""
        log.info("JARVIS останавливается...")
        keyboard.unhook_all()
        self.listener.stop()
        self.speaker.stop()
        self.tray.hide()

    def _wire_signals(self) -> None:
        self.tray.open_requested.connect(self._show_overlay)
        self.tray.settings_requested.connect(self._show_settings)
        self.tray.pause_requested.connect(self._toggle_pause)
        self.tray.restart_requested.connect(self._restart)
        self.tray.quit_requested.connect(self._quit)
        self.tray.interview_toggle_requested.connect(self._toggle_interview_mode)
        self.tray.interview_setup_requested.connect(self._show_interview_setup)
        self.tray.rescan_requested.connect(self._rescan_system)
        self.tray.interview_live_requested.connect(self._toggle_interview_live)

    def _setup_hotkey(self) -> None:
        """Горячая клавиша Ctrl+J."""
        try:
            keyboard.add_hotkey("ctrl+j", self._on_hotkey, suppress=False)
            log.info("Горячая клавиша Ctrl+J зарегистрирована")
        except Exception as e:
            log.error("hotkey: %s", e)

    def _setup_interview_hotkeys(self) -> None:
        """Горячие клавиши режима собеседования."""
        try:
            keyboard.add_hotkey(
                "ctrl+shift+i",
                self._interview_capture,
                suppress=False,
            )
            keyboard.add_hotkey(
                "ctrl+shift+v",
                self._interview_from_clipboard,
                suppress=False,
            )
            keyboard.add_hotkey(
                "ctrl+shift+l",
                self._toggle_interview_live,
                suppress=False,
            )
            log.info("Interview hotkeys: Ctrl+Shift+L (LIVE), Ctrl+Shift+I, Ctrl+Shift+V")
        except Exception as e:
            log.error("interview hotkeys: %s", e)

    def _interview_capture(self) -> None:
        if self.interview.active:
            self.interview.capture_question()

    def _interview_from_clipboard(self) -> None:
        if not self.interview.active:
            return
        import pyperclip
        text = pyperclip.paste()
        if text:
            self.interview.process_text_question(text)

    def _toggle_interview_live(self) -> None:
        """Включить/выключить LIVE — захват звука Zoom/Meet/Teams."""
        if not self.interview.active:
            self.tray.showMessage(
                "JARVIS",
                "Сначала включите режим собеседования в трее.",
                QSystemTrayIcon.MessageIcon.Warning,
                2500,
            )
            return

        if not self.interview.live:
            if not INTERVIEW_DISCLAIMER_FLAG.exists():
                from PyQt6.QtWidgets import QMessageBox
                r = QMessageBox.warning(
                    None,
                    "Режим собеседования",
                    "JARVIS подсказывает ответы только Вам (невидимая панель).\n\n"
                    "Используйте для подготовки и mock-интервью.\n"
                    "Наденьте наушники — JARVIS слушает звук созвона.\n\n"
                    "Продолжить?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if r != QMessageBox.StandardButton.Yes:
                    return
                INTERVIEW_DISCLAIMER_FLAG.touch()

        ok, msg = self.interview.toggle_live()
        self.tray.set_interview_live(self.interview.live)
        icon = (
            QSystemTrayIcon.MessageIcon.Information
            if ok or not self.interview.live
            else QSystemTrayIcon.MessageIcon.Warning
        )
        self.tray.showMessage("JARVIS · LIVE", msg, icon, 3500)

    def _toggle_interview_mode(self) -> None:
        if self.interview.active:
            self.interview.disable()
            self.tray.set_interview_mode(False)
            self.tray.set_interview_live(False)
            if not self._minimized:
                self.overlay.show_overlay()
            self.tray.showMessage(
                "JARVIS",
                "Режим собеседования выключен.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            from ui.interview_setup import load_interview_profile
            profile = load_interview_profile()
            if not profile.get("resume") and not profile.get("skills"):
                self._show_interview_setup()
            self.interview.enable()
            self.tray.set_interview_mode(True)
            self.overlay.hide_overlay()
            self.tray.showMessage(
                "JARVIS · Собеседование",
                "Профиль загружен. Когда созвон начнётся — Ctrl+Shift+L (LIVE).\n"
                "Наденьте наушники! JARVIS услышит рекрутера из Zoom/Meet/Teams.",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )

    def _show_interview_setup(self) -> None:
        from ui.interview_setup import InterviewSetupDialog
        InterviewSetupDialog().exec()

    def _rescan_system(self) -> None:
        """Пересканировать компьютер по запросу из трея."""
        def _run():
            meta = scan_all(force=True)
            self.tray.showMessage(
                "JARVIS",
                f"Сканирование завершено: {meta.get('count', 0)} элементов.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

        threading.Thread(target=_run, daemon=True).start()
        self.tray.showMessage(
            "JARVIS",
            "Сканирование компьютера запущено...",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _on_interview_mode_changed(self, enabled: bool) -> None:
        if enabled:
            self.listener.pause()
        else:
            if not self.tray.is_paused():
                self.listener.resume()

    def _on_hotkey(self) -> None:
        if self.interview.active:
            return
        if self.tray.is_paused():
            log.info("Ctrl+J: JARVIS на паузе")
            self.tray.showMessage(
                "JARVIS",
                "На паузе. Трей → Возобновить.",
                QSystemTrayIcon.MessageIcon.Warning,
                2500,
            )
            return
        if not self._processing:
            log.info("Ctrl+J: активация")
            self._on_wake()

    def _on_wake(self) -> None:
        """Обработка wake word или Ctrl+J."""
        if self.interview.active:
            return
        with self._lock:
            if self._processing or self.tray.is_paused():
                return
            self._processing = True

        self.listener.pause()
        threading.Thread(target=self._handle_wake_flow, daemon=True).start()

    def _handle_wake_flow(self) -> None:
        """Полный цикл: активация → запись → обработка."""
        hide_after = False
        try:
            if self._minimized:
                hide_after = True
                QTimer.singleShot(0, self.overlay.show_overlay)

            self.tray.showMessage(
                "JARVIS",
                "Слушаю Вас...",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            self.speaker.play_sound("activate")
            self._set_state(AssistantState.LISTENING)
            self.speaker.say_cached("listening")
            self.speaker.wait_until_done(timeout=6.0)
            time.sleep(0.6)

            command = self.listener.consume_command_hint()
            if not command:
                command = self.listener.listen_command()
            if not command:
                self.speaker.say_cached("not_understood")
                self._set_state(AssistantState.SLEEPING)
                return

            log.info("Распознанная команда: %s", command)
            self.overlay.set_command_text(command)
            self._set_state(AssistantState.THINKING)

            # Обработка
            response, needs_confirm, coding = self.router.process(command)

            if needs_confirm:
                self._handle_confirmation(response)
                return

            self._speak_response(response)

            if coding and coding.code:
                self._on_code_result(coding)

        except Exception as e:
            log.error("wake flow: %s", e)
            self.speaker.say_cached("error", detail=str(e))
            self._set_state(AssistantState.SLEEPING)
        finally:
            with self._lock:
                self._processing = False
            if not self.interview.active and not self.tray.is_paused():
                self.listener.resume()
            self.speaker.play_sound("deactivate")
            if hide_after:
                QTimer.singleShot(0, self.overlay.hide_overlay)

    def _handle_confirmation(self, prompt: str) -> None:
        """Ожидание голосового подтверждения."""
        self._set_state(AssistantState.CONFIRMING)
        self.speaker.say(prompt or "")
        self.speaker.say_cached("confirm")

        confirmed = self.listener.listen_confirmation(
            timeout=settings.confirm_timeout
        )

        if confirmed:
            result = self.router.confirm_pending()
            self._speak_response(result)
        else:
            self.router.cancel_pending()
            self.speaker.say_cached("cancelled")
            self._set_state(AssistantState.SLEEPING)

    def _speak_response(self, text: str) -> None:
        """Озвучить ответ."""
        if not text:
            return
        self._set_state(AssistantState.SPEAKING)
        self.speaker.say(text, block=True)
        self._set_state(AssistantState.SLEEPING)

    def _on_code_result(self, coding: CodingResult) -> None:
        """Показать панель с кодом."""
        if coding.code:
            self.overlay.show_code(coding.code, coding.language)

    def _set_state(self, state: AssistantState) -> None:
        self._state = state
        ui_state = state.value
        self.overlay.set_state(ui_state)

        tray_map = {
            AssistantState.SLEEPING: JarvisTray.STATE_SLEEPING,
            AssistantState.LISTENING: JarvisTray.STATE_LISTENING,
            AssistantState.THINKING: JarvisTray.STATE_LISTENING,
            AssistantState.SPEAKING: JarvisTray.STATE_SPEAKING,
            AssistantState.CONFIRMING: JarvisTray.STATE_LISTENING,
        }
        self.tray.set_state(tray_map.get(state, JarvisTray.STATE_SLEEPING))

    def _on_speaking(self, speaking: bool) -> None:
        if speaking and self._state != AssistantState.CONFIRMING:
            self._set_state(AssistantState.SPEAKING)

    def _on_audio_level(self, level: float) -> None:
        self.overlay.set_audio_level(level)

    def _on_listening_flag(self, listening: bool) -> None:
        if listening:
            self._set_state(AssistantState.LISTENING)

    def _background_scan(self) -> None:
        from core.local_intent import refresh_from_index
        from skills.system_indexer import get_index_meta, scan_all, should_rescan

        def on_progress(msg: str) -> None:
            log.debug("Сканирование: %s", msg)

        try:
            meta = get_index_meta()
            if should_rescan():
                log.info("Сканирование ПК при запуске...")
                meta = scan_all(on_progress=on_progress)
            else:
                log.info(
                    "Индекс актуален: %d элементов (сканирование пропущено)",
                    meta.get("count", 0),
                )

            count = refresh_from_index()
            self.tray.showMessage(
                "JARVIS",
                f"Готов: {count} программ и файлов в индексе.",
                QSystemTrayIcon.MessageIcon.Information,
                3500,
            )
        except Exception as e:
            log.error("background scan: %s", e)

    def _show_overlay(self) -> None:
        self.overlay.show_overlay()

    def _show_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(speaker=self.speaker)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self.brain.set_title(settings.user_title)
            self.overlay.apply_position()

    def _toggle_pause(self) -> None:
        if self.tray.is_paused():
            self.listener.pause()
            self._set_state(AssistantState.SLEEPING)
            self.tray.showMessage(
                "JARVIS",
                "Приостановлен. В трее: Возобновить.",
                QSystemTrayIcon.MessageIcon.Warning,
                2500,
            )
        else:
            self.listener.resume()
            self.tray.showMessage(
                "JARVIS",
                "Снова слушаю микрофон.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def _restart(self) -> None:
        import sys
        import os
        log.info("Перезапуск JARVIS...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _quit(self) -> None:
        from PyQt6.QtWidgets import QApplication
        self.stop()
        QApplication.instance().quit()
