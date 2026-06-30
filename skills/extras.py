"""Дополнительные навыки: скриншот, буфер, таймер, системная информация."""

import threading
from datetime import datetime
from pathlib import Path

import psutil
import pyautogui
import pyperclip
from PIL import Image

from config.settings import log, save_history_entry

# Активные таймеры
_timers: list[threading.Timer] = []


def take_screenshot() -> str:
    """Скриншот экрана в папку Изображения."""
    try:
        pictures = Path.home() / "Pictures"
        pictures.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = pictures / f"jarvis_screenshot_{timestamp}.png"

        screenshot = pyautogui.screenshot()
        screenshot.save(str(path))
        return f"Скриншот сохранён: {path.name}."
    except Exception as e:
        log.error("screenshot: %s", e)
        return "Не удалось сделать скриншот."


def read_clipboard() -> str:
    """Прочитать содержимое буфера обмена."""
    try:
        text = pyperclip.paste()
        if not text:
            return "Буфер обмена пуст."
        # Ограничиваем длину для озвучивания
        if len(text) > 300:
            return f"В буфере обмена: {text[:300]}... и ещё {len(text) - 300} символов."
        return f"В буфере обмена: {text}"
    except Exception as e:
        log.error("clipboard: %s", e)
        return "Не удалось прочитать буфер обмена."


def get_sysinfo() -> str:
    """Системная информация: CPU, RAM, диск."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        return (
            f"Загрузка процессора {cpu:.0f} процентов. "
            f"Оперативная память: используется {mem.percent:.0f} процентов, "
            f"свободно {mem.available // (1024**3)} гигабайт. "
            f"Диск C: занято {disk.percent:.0f} процентов."
        )
    except Exception as e:
        log.error("sysinfo: %s", e)
        return "Не удалось получить системную информацию."


def set_timer(minutes: int, text: str, callback) -> str:
    """Установить таймер/напоминание."""
    if minutes <= 0:
        return "Укажите время в минутах."

    def _notify():
        try:
            callback(text or "Время вышло.")
        except Exception as e:
            log.error("timer callback: %s", e)

    timer = threading.Timer(minutes * 60, _notify)
    timer.daemon = True
    timer.start()
    _timers.append(timer)

    msg = f"Напоминание через {minutes} минут"
    if text:
        msg += f": {text}"
    return msg + "."


def log_command(command: str, response: str) -> None:
    """Записать команду в историю."""
    try:
        save_history_entry(command, response)
    except Exception as e:
        log.error("log_command: %s", e)
