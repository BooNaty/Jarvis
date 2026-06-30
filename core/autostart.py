"""Автозапуск JARVIS через реестр Windows."""

import sys
import winreg

from config.settings import BASE_DIR, log


APP_NAME = "Jarvis"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_exe_path() -> str:
    """Путь к исполняемому файлу с флагом --minimized."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
    else:
        exe = str(BASE_DIR / "main.py")
        return f'"{sys.executable}" "{exe}" --minimized'
    return f'"{exe}" --minimized'


def enable_autostart() -> bool:
    """Включить автозапуск при старте Windows."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        log.info("Автозапуск включён")
        return True
    except Exception as e:
        log.error("enable_autostart: %s", e)
        return False


def disable_autostart() -> bool:
    """Отключить автозапуск."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        log.info("Автозапуск отключён")
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        log.error("disable_autostart: %s", e)
        return False


def is_autostart_enabled() -> bool:
    """Проверить, включён ли автозапуск."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False
