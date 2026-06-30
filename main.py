"""Точка входа JARVIS Voice Assistant."""

# PyAudio на Python 3.14: используем pyaudiowpatch как замену
try:
    import pyaudio  # noqa: F401
except ImportError:
    import pyaudiowpatch as pyaudio
    import sys

    sys.modules["pyaudio"] = pyaudio

import argparse
import sys

from config.settings import is_setup_complete, log
from core.single_instance import try_acquire_instance
from ui.setup_wizard import SetupWizard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS Voice Assistant")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Запуск сразу в системный трей",
    )
    parser.add_argument(
        "--watchdog",
        action="store_true",
        help="Запуск в режиме watchdog",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.watchdog:
        from core.watchdog import run_watchdog
        run_watchdog()
        return 0

    if not try_acquire_instance():
        return 0

    from PyQt6.QtWidgets import QApplication

    from core.assistant import Assistant

    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS")
    app.setQuitOnLastWindowClosed(False)

    # Мастер настройки при первом запуске
    if not is_setup_complete():
        log.info("Первый запуск — мастер настройки")
        from core.speaker import Speaker
        wizard = SetupWizard(speaker=Speaker())
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            return 0

    assistant = Assistant(minimized=args.minimized)
    assistant.start()

    log.info("JARVIS работает")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
