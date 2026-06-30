"""Запрет второго экземпляра JARVIS — иначе ПК зависает."""

from __future__ import annotations

import atexit
import os
from pathlib import Path

from config.settings import CONFIG_DIR, log

LOCK_PATH = CONFIG_DIR / ".jarvis.lock"
MUTEX_NAME = "Global\\JarvisAssistant_SingleInstance"

_mutex_handle = None


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        return False


def _read_lock_pid() -> int | None:
    try:
        return int(LOCK_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _acquire_pid_lock() -> bool:
    if LOCK_PATH.exists():
        old_pid = _read_lock_pid()
        if old_pid and _pid_running(old_pid):
            return False
        try:
            LOCK_PATH.unlink()
        except OSError:
            return False

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        return False


def _release_pid_lock() -> None:
    try:
        if LOCK_PATH.exists() and _read_lock_pid() == os.getpid():
            LOCK_PATH.unlink()
    except OSError:
        pass


def _acquire_mutex() -> bool:
    global _mutex_handle
    try:
        import win32api
        import win32event
    except ImportError:
        return True

    _mutex_handle = win32event.CreateMutex(None, True, MUTEX_NAME)
    if win32api.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        win32api.CloseHandle(_mutex_handle)
        _mutex_handle = None
        return False
    return True


def _release_mutex() -> None:
    global _mutex_handle
    if _mutex_handle is not None:
        try:
            import win32api

            win32api.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None


def try_acquire_instance() -> bool:
    """
    True — можно запускаться.
    False — JARVIS уже работает.
    """
    if not _acquire_mutex():
        log.info("JARVIS уже запущен (mutex)")
        return False

    if not _acquire_pid_lock():
        log.info("JARVIS уже запущен (lock file)")
        _release_mutex()
        return False

    atexit.register(_release_all)
    return True


def _release_all() -> None:
    _release_pid_lock()
    _release_mutex()


def force_release_lock_files() -> None:
    """Аварийная очистка — для stop_jarvis.ps1."""
    _release_all()
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except OSError:
        pass
