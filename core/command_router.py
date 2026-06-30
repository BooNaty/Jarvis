"""Маршрутизация интентов к навыкам."""

from typing import Callable, Optional

from config.settings import log, settings
from core.brain import Brain, CodingResult, IntentResult
from core.intent_resolver import resolve_intent
from skills import (
    app_launcher,
    browser_control,
    coding_helper,
    extras,
    file_manager,
    pc_control,
    steam_control,
    system_control,
)


# Интенты через intent_resolver (см. core/intent_resolver.py)


class CommandRouter:
    """Направляет распознанные команды к соответствующим навыкам."""

    def __init__(self, brain: Brain, on_code: Optional[Callable] = None,
                 on_timer: Optional[Callable[[str], None]] = None):
        self._brain = brain
        self._on_code = on_code
        self._on_timer = on_timer
        self._pending_intent: Optional[IntentResult] = None

    @property
    def pending_confirm(self) -> bool:
        return self._pending_intent is not None

    def process(self, command: str) -> tuple[str, bool, Optional[CodingResult]]:
        """
        Обработать команду.
        Возвращает: (ответ для озвучивания, нужно_ли_подтверждение, результат_кода)
        """
        log.info("Команда: %s", command)
        intent = resolve_intent(self._brain, command)

        if intent.intent == "coding_help":
            return self._handle_coding(command)

        if intent.needs_confirm:
            self._pending_intent = intent
            return intent.response, True, None

        result = self._execute_intent(intent)
        extras.log_command(command, result)
        return result, False, None

    def confirm_pending(self) -> str:
        """Выполнить отложенную команду после подтверждения."""
        if not self._pending_intent:
            return "Нет команды для подтверждения."
        intent = self._pending_intent
        self._pending_intent = None
        result = self._execute_intent(intent)
        extras.log_command("confirm", result)
        return result

    def cancel_pending(self) -> str:
        """Отменить отложенную команду."""
        self._pending_intent = None
        return "Команда отменена."

    def _handle_coding(self, command: str) -> tuple[str, bool, Optional[CodingResult]]:
        """Режим помощи с кодом."""
        coding = self._brain.coding_help(command)
        if coding.code:
            coding_helper.save_code(coding.code, coding.language)
            if self._on_code:
                self._on_code(coding)
        extras.log_command(command, coding.summary)
        return coding.summary, False, coding

    def _execute_intent(self, intent: IntentResult) -> str:
        """Выполнить интент."""
        i = intent.intent
        p = intent.params
        default = intent.response

        try:
            if i == "open_app":
                return pc_control.open_on_pc(p.get("app_name", ""))

            if i == "open_file":
                return pc_control.open_on_pc(p.get("query", ""))

            if i == "find_local":
                return pc_control.find_on_pc(p.get("query", ""))

            if i == "find_in_folder":
                return pc_control.find_in_folder(
                    p.get("folder", ""), p.get("query", "")
                )

            if i == "play_media":
                return pc_control.play_media(p.get("query", ""))

            if i == "read_file":
                return pc_control.read_local_file(p.get("query", ""))

            if i == "media_play":
                return pc_control.media_play_pause()

            if i == "media_pause":
                return pc_control.media_play_pause()

            if i == "media_next":
                return pc_control.media_next()

            if i == "media_prev":
                return pc_control.media_previous()

            if i == "media_stop":
                return pc_control.media_stop()

            if i == "open_browser":
                return browser_control.open_browser()

            if i == "search_web":
                return browser_control.search_web(p.get("query", ""))

            if i == "weather":
                return browser_control.get_weather(p.get("city", "Москва"))

            if i == "youtube":
                return browser_control.search_youtube(p.get("query", ""))

            if i == "volume_set":
                return system_control.set_volume(int(p.get("percent", 50)))

            if i == "volume_up":
                return system_control.volume_up(int(p.get("percent", 10)))

            if i == "volume_down":
                return system_control.volume_down(int(p.get("percent", 10)))

            if i == "mute":
                return system_control.mute()

            if i == "brightness_set":
                val = p.get("percent", p.get("value", 50))
                if str(val).lower() in ("max", "максимум", "maximum"):
                    return system_control.brightness_max()
                if str(val).lower() in ("min", "минимум", "minimum"):
                    return system_control.brightness_min()
                return system_control.set_brightness(int(val))

            if i == "brightness_up":
                return system_control.brightness_up(int(p.get("step", 15)))

            if i == "brightness_down":
                return system_control.brightness_down(int(p.get("step", 15)))

            if i == "close_app":
                return pc_control.close_app(p.get("app_name", ""))

            if i == "shutdown":
                return system_control.shutdown_pc()

            if i == "restart":
                return system_control.restart_pc()

            if i == "sleep":
                return system_control.sleep_pc()

            if i == "cancel_shutdown":
                return system_control.cancel_shutdown()

            if i == "open_steam":
                return steam_control.open_steam()

            if i == "launch_game":
                return steam_control.launch_game(p.get("game_name", ""))

            if i == "open_folder":
                return file_manager.open_folder(
                    p.get("folder", p.get("path", ""))
                )

            if i == "screenshot":
                return extras.take_screenshot()

            if i == "clipboard":
                return extras.read_clipboard()

            if i == "sysinfo":
                return extras.get_sysinfo()

            if i == "timer":
                cb = self._on_timer or (lambda t: None)
                return extras.set_timer(
                    int(p.get("minutes", 1)),
                    p.get("text", ""),
                    cb,
                )

            if i == "reminder":
                cb = self._on_timer or (lambda t: None)
                return extras.set_timer(
                    int(p.get("minutes", 5)),
                    p.get("text", "Напоминание"),
                    cb,
                )

            if i == "unknown":
                return default or "Прошу прощения, я не понял команду."

            return default or f"Интент {i} не реализован."

        except Exception as e:
            log.error("execute_intent %s: %s", i, e)
            return f"Произошла ошибка при выполнении: {e}"

