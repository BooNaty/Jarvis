"""Watchdog: следит за процессом jarvis и перезапускает при падении."""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

from config.settings import CRASHES_LOG, log, settings

WATCHDOG_NAME = "jarvis_watchdog"


def _is_jarvis_running() -> bool:
    """Проверить, запущен ли процесс JARVIS."""
    current_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            name = (proc.info["name"] or "").lower()
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()

            if "jarvis" in name or "jarvis" in cmd_str:
                if "watchdog" not in cmd_str:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _get_jarvis_cmd() -> list[str]:
    """Команда для запуска JARVIS."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--minimized"]
    base = Path(__file__).resolve().parent.parent
    return [sys.executable, str(base / "main.py"), "--minimized"]


def _log_crash(message: str) -> None:
    """Записать в лог падений."""
    CRASHES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CRASHES_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} — {message}\n")


def run_watchdog() -> None:
    """Основной цикл watchdog."""
    log.info("Watchdog запущен (интервал %d сек)", settings.watchdog_interval)
    jarvis_cmd = _get_jarvis_cmd()

    while True:
        if not _is_jarvis_running():
            _log_crash("JARVIS не обнаружен, перезапуск...")
            log.warning("JARVIS упал, перезапускаю...")
            try:
                subprocess.Popen(
                    jarvis_cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                )
            except Exception as e:
                _log_crash(f"Ошибка перезапуска: {e}")
                log.error("watchdog restart: %s", e)

        time.sleep(settings.watchdog_interval)


if __name__ == "__main__":
    run_watchdog()
