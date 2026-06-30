"""Работа с папками и файлами."""

import os
import subprocess
from pathlib import Path

from config.settings import log

# Стандартные папки Windows
FOLDERS = {
    "загрузки": Path.home() / "Downloads",
    "downloads": Path.home() / "Downloads",
    "документы": Path.home() / "Documents",
    "documents": Path.home() / "Documents",
    "рабочий стол": Path.home() / "Desktop",
    "desktop": Path.home() / "Desktop",
    "стол": Path.home() / "Desktop",
    "музыка": Path.home() / "Music",
    "music": Path.home() / "Music",
    "видео": Path.home() / "Videos",
    "videos": Path.home() / "Videos",
    "изображения": Path.home() / "Pictures",
    "pictures": Path.home() / "Pictures",
    "фото": Path.home() / "Pictures",
}


def open_folder(name_or_path: str) -> str:
    """Открыть папку по имени или пути."""
    if not name_or_path:
        return "Не указана папка."

    query = name_or_path.lower().strip()

    # Стандартная папка
    if query in FOLDERS:
        path = FOLDERS[query]
        if path.exists():
            _open_explorer(path)
            return f"Открываю папку {query}."
        return f"Папка {query} не найдена."

    # Абсолютный или относительный путь
    path = Path(name_or_path)
    if path.exists() and path.is_dir():
        _open_explorer(path)
        return f"Открываю {path}."

    # Поиск в домашней директории
    home = Path.home()
    for item in home.iterdir():
        if item.is_dir() and query in item.name.lower():
            _open_explorer(item)
            return f"Открываю {item.name}."

    return f"Папка «{name_or_path}» не найдена."


def _open_explorer(path: Path) -> None:
    """Открыть папку в проводнике."""
    try:
        subprocess.Popen(["explorer.exe", str(path)], shell=False)
    except Exception as e:
        log.error("open_explorer: %s", e)
        os.startfile(str(path))
