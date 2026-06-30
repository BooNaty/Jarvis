"""Запуск приложений и файлов через полный индекс системы."""

import os
import subprocess

from rapidfuzz import fuzz, process

from config.settings import load_apps_registry, log, save_apps_registry
from skills import system_indexer

# Быстрый поиск популярных приложений (fallback)
AUTO_DISCOVER = {
    "chrome": {
        "names": ["хром", "chrome", "гугл хром", "google chrome", "браузер"],
        "paths": [r"Google\Chrome\Application\chrome.exe"],
    },
    "vscode": {
        "names": ["vscode", "vs code", "visual studio code"],
        "paths": [r"Microsoft VS Code\Code.exe", r"Programs\Microsoft VS Code\Code.exe"],
    },
    "cursor": {
        "names": ["cursor", "курсор"],
        "paths": [r"Programs\cursor\Cursor.exe"],
    },
    "telegram": {
        "names": ["telegram", "телеграм", "телега"],
        "paths": [r"Telegram Desktop\Telegram.exe"],
    },
    "discord": {
        "names": ["discord", "дискорд"],
        "paths": [r"Discord\app\Discord.exe"],
    },
    "explorer": {
        "names": ["проводник", "explorer", "файлы"],
        "fixed": "explorer.exe",
    },
}


def discover_apps() -> dict:
    """Быстрый поиск популярных приложений + запуск полного скана в фоне."""
    registry = load_apps_registry()
    from pathlib import Path
    import os

    bases = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("LOCALAPPDATA", "")),
    ]

    for app_id, info in AUTO_DISCOVER.items():
        if registry.get(app_id, {}).get("path"):
            continue
        path = info.get("fixed", "")
        if not path:
            for base in bases:
                for rel in info.get("paths", []):
                    full = base / rel
                    if full.exists():
                        path = str(full)
                        break
                if path:
                    break
        if path:
            registry[app_id] = {"names": info["names"], "path": path}

    save_apps_registry(registry)
    return registry


def launch_app(app_name: str) -> str:
    """
    Запустить приложение/файл/игру по имени.
    Сначала — полный индекс системы, затем fallback.
    """
    if not app_name.strip():
        return "Не указано, что открыть."

    # 1. Полный индекс (сканирует всё на ПК)
    result = system_indexer.search_and_launch(app_name)
    if "не найдено" not in result.lower():
        return result

    # 2. Старый реестр apps_registry.json
    registry = load_apps_registry()
    index: dict[str, tuple[str, str]] = {}
    for app_id, info in registry.items():
        path = info.get("path", "")
        if not path:
            continue
        for name in info.get("names", [app_id]):
            index[name.lower()] = (app_id, path)

    if index:
        from rapidfuzz import process as rf_process
        match = rf_process.extractOne(app_name.lower(), list(index.keys()), scorer=fuzz.WRatio)
        if match and match[1] >= 60:
            app_id, path = index[match[0]]
            try:
                os.startfile(path)
                return f"Запускаю {app_id}."
            except Exception as e:
                log.error("launch_app registry: %s", e)

    # 3. where в PATH
    try:
        r = subprocess.run(
            ["where", f"{app_name.strip()}.exe"],
            capture_output=True, text=True, timeout=5, shell=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            os.startfile(r.stdout.strip().split("\n")[0])
            return f"Запускаю {app_name}."
    except Exception as e:
        log.debug("where fallback: %s", e)

    return f"«{app_name}» не найдено. Запустите сканирование из трея или подождите — индекс строится в фоне."
