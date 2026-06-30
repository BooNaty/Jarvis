"""Управление громкостью, яркостью и питанием Windows."""

import subprocess
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from config.settings import log


def _get_volume_interface():
    """Получить интерфейс управления громкостью."""
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume_percent() -> int:
    """Текущая громкость в процентах."""
    try:
        vol = _get_volume_interface()
        return int(vol.GetMasterVolumeLevelScalar() * 100)
    except Exception as e:
        log.error("get_volume: %s", e)
        return 50


def set_volume(percent: int) -> str:
    """Установить громкость 0-100%."""
    try:
        percent = max(0, min(100, percent))
        vol = _get_volume_interface()
        vol.SetMasterVolumeLevelScalar(percent / 100.0, None)
        return f"Громкость установлена на {percent} процентов."
    except Exception as e:
        log.error("set_volume: %s", e)
        return "Не удалось изменить громкость."


def volume_up(percent: int = 10) -> str:
    """Увеличить громкость."""
    current = get_volume_percent()
    return set_volume(min(100, current + percent))


def volume_down(percent: int = 10) -> str:
    """Уменьшить громкость."""
    current = get_volume_percent()
    return set_volume(max(0, current - percent))


def mute() -> str:
    """Выключить/включить звук."""
    try:
        vol = _get_volume_interface()
        muted = vol.GetMute()
        vol.SetMute(not muted, None)
        return "Звук выключен." if not muted else "Звук включён."
    except Exception as e:
        log.error("mute: %s", e)
        return "Не удалось переключить звук."


def get_brightness() -> int:
    """Текущая яркость."""
    try:
        import screen_brightness_control as sbc
        return sbc.get_brightness()[0]
    except Exception as e:
        log.error("get_brightness: %s", e)
        return 50


def set_brightness(percent: int) -> str:
    """Установить яркость 0-100%."""
    try:
        import screen_brightness_control as sbc
        percent = max(0, min(100, percent))
        sbc.set_brightness(percent)
        return f"Яркость установлена на {percent} процентов."
    except Exception as e:
        log.error("set_brightness: %s", e)
        return "Не удалось изменить яркость."


def brightness_max() -> str:
    return set_brightness(100)


def brightness_min() -> str:
    return set_brightness(0)


def brightness_up(step: int = 15) -> str:
    """Увеличить яркость на step%."""
    try:
        current = get_brightness()
        return set_brightness(min(100, current + step))
    except Exception as e:
        log.error("brightness_up: %s", e)
        return "Не удалось изменить яркость."


def brightness_down(step: int = 15) -> str:
    """Уменьшить яркость на step%."""
    try:
        current = get_brightness()
        return set_brightness(max(0, current - step))
    except Exception as e:
        log.error("brightness_down: %s", e)
        return "Не удалось изменить яркость."


def shutdown_pc() -> str:
    """Выключение через 10 секунд."""
    try:
        subprocess.Popen(["shutdown", "/s", "/t", "10"], shell=False)
        return "Компьютер будет выключен через 10 секунд."
    except Exception as e:
        log.error("shutdown: %s", e)
        return "Не удалось запустить выключение."


def restart_pc() -> str:
    """Перезагрузка через 10 секунд."""
    try:
        subprocess.Popen(["shutdown", "/r", "/t", "10"], shell=False)
        return "Компьютер будет перезагружен через 10 секунд."
    except Exception as e:
        log.error("restart: %s", e)
        return "Не удалось запустить перезагрузку."


def sleep_pc() -> str:
    """Спящий режим."""
    try:
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"],
            shell=False,
        )
        return "Перевожу в спящий режим."
    except Exception as e:
        log.error("sleep: %s", e)
        return "Не удалось перевести в спящий режим."


def cancel_shutdown() -> str:
    """Отмена запланированного выключения."""
    try:
        subprocess.Popen(["shutdown", "/a"], shell=False)
        return "Выключение отменено."
    except Exception as e:
        log.error("cancel_shutdown: %s", e)
        return "Не удалось отменить выключение."
