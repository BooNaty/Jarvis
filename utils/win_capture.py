"""Скрытие окна от захвата экрана (Zoom, Teams, OBS, Discord)."""

import ctypes
import sys
from typing import Optional

from config.settings import log

# Windows 10 2004+: окно не попадает в screen share / запись экрана
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011


def exclude_from_capture(hwnd: int, exclude: bool = True) -> bool:
    """
    Сделать окно невидимым при шеринге экрана.
    Работает на Windows 10 2004+.
    """
    if sys.platform != "win32":
        log.warning("exclude_from_capture: только Windows")
        return False

    try:
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
        if result:
            log.debug("Display affinity %s для hwnd %s", affinity, hwnd)
            return True
        log.error("SetWindowDisplayAffinity failed for hwnd %s", hwnd)
        return False
    except Exception as e:
        log.error("exclude_from_capture: %s", e)
        return False


def apply_to_qt_window(widget, exclude: bool = True) -> bool:
    """Применить к PyQt6 виджету."""
    try:
        hwnd = int(widget.winId())
        return exclude_from_capture(hwnd, exclude)
    except Exception as e:
        log.error("apply_to_qt_window: %s", e)
        return False
