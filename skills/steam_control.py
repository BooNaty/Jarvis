"""Управление Steam и запуск игр."""

import os
import re
import winreg
from pathlib import Path

import vdf
from rapidfuzz import fuzz, process

from config.settings import log, settings

_games_cache: list[dict] | None = None
_steam_path: str | None = None


def _find_steam_path() -> str:
    """Найти путь к Steam через реестр."""
    global _steam_path
    if _steam_path:
        return _steam_path

    if settings.steam_path and settings.steam_path != "auto":
        if os.path.exists(settings.steam_path):
            _steam_path = settings.steam_path
            return _steam_path

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "SteamPath")
            steam_exe = os.path.join(value, "steam.exe")
            if os.path.exists(steam_exe):
                _steam_path = steam_exe
                return _steam_path
    except OSError:
        pass

    # Стандартные пути
    for path in [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
    ]:
        if os.path.exists(path):
            _steam_path = path
            return _steam_path

    return ""


def _get_library_folders(steam_dir: str) -> list[str]:
    """Получить все папки библиотек Steam."""
    vdf_path = os.path.join(steam_dir, "steamapps", "libraryfolders.vdf")
    folders = [os.path.join(steam_dir, "steamapps")]

    if not os.path.exists(vdf_path):
        return folders

    try:
        with open(vdf_path, "r", encoding="utf-8") as f:
            data = vdf.load(f)

        libs = data.get("libraryfolders", data.get("LibraryFolders", {}))
        for key, val in libs.items():
            if key.isdigit() and isinstance(val, dict):
                lib_path = val.get("path", "")
                if lib_path:
                    folders.append(os.path.join(lib_path, "steamapps"))
    except Exception as e:
        log.error("libraryfolders.vdf: %s", e)

    return folders


def _parse_games() -> list[dict]:
    """Собрать список игр из appmanifest_*.acf."""
    global _games_cache
    if _games_cache is not None:
        return _games_cache

    steam_exe = _find_steam_path()
    if not steam_exe:
        _games_cache = []
        return _games_cache

    steam_dir = os.path.dirname(steam_exe)
    games: list[dict] = []

    for lib_folder in _get_library_folders(steam_dir):
        if not os.path.isdir(lib_folder):
            continue
        for fname in os.listdir(lib_folder):
            if not fname.startswith("appmanifest_") or not fname.endswith(".acf"):
                continue
            manifest_path = os.path.join(lib_folder, fname)
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = vdf.load(f)
                app_state = data.get("AppState", {})
                appid = app_state.get("appid", "")
                name = app_state.get("name", "")
                if appid and name:
                    games.append({"appid": str(appid), "name": name})
            except Exception as e:
                log.debug("manifest %s: %s", fname, e)

    _games_cache = games
    log.info("Найдено игр Steam: %d", len(games))
    return games


def open_steam() -> str:
    """Открыть Steam."""
    steam = _find_steam_path()
    if not steam:
        return "Steam не найден на этом компьютере."
    try:
        os.startfile("steam://open/main")
        return "Открываю Steam."
    except Exception as e:
        log.error("open_steam: %s", e)
        return "Не удалось открыть Steam."


def launch_game(game_name: str) -> str:
    """Запустить игру по названию."""
    games = _parse_games()
    if not games:
        return "Игры Steam не найдены."

    names = [g["name"] for g in games]
    match = process.extractOne(game_name, names, scorer=fuzz.WRatio)

    if match and match[1] >= 55:
        idx = names.index(match[0])
        appid = games[idx]["appid"]
        try:
            os.startfile(f"steam://rungameid/{appid}")
            return f"Запускаю {match[0]}."
        except Exception as e:
            log.error("launch_game: %s", e)
            return f"Не удалось запустить {match[0]}."

    return f"Игра «{game_name}» не найдена в библиотеке Steam."


def get_steam_info() -> str:
    """Информация о Steam для мастера настройки."""
    steam = _find_steam_path()
    if steam:
        games = _parse_games()
        return f"Steam найден: {steam}, игр: {len(games)}"
    return "Steam не найден."
