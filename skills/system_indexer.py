"""Полное сканирование ПК: приложения, ярлыки, игры, файлы."""

import json
import os
import re
import subprocess
import threading
import time
import winreg
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz, process

from config.settings import CONFIG_DIR, log

INDEX_PATH = CONFIG_DIR / "system_index.json"
INDEX_LOCK = threading.Lock()

# Лимиты чтобы скан не занял часы
MAX_ITEMS = 8000
MAX_EXE_DEPTH = 4
MAX_FILE_DEPTH = 3
SKIP_DIRS = {
    "windows", "program files", "program files (x86)", "$recycle.bin",
    "node_modules", ".git", "__pycache__", "venv", ".venv", "appdata\\local\\temp",
    "microsoft", "packages", "winsxs", "system volume information",
}

_index_cache: list[dict] | None = None
_scanning = False


def _normalize_name(path: str) -> str:
    return Path(path).stem.lower().replace("_", " ").replace("-", " ")


def _add_item(items: dict, name: str, path: str, kind: str, source: str) -> bool:
    """Добавить элемент в индекс (без дубликатов по path)."""
    if len(items) >= MAX_ITEMS:
        return False
    if not path or not name:
        return False
    path = os.path.normpath(path)
    if not os.path.exists(path) and kind != "url":
        return False

    key = path.lower()
    if key in items:
        return True

    clean_name = name.strip()
    aliases = {_normalize_name(clean_name), _normalize_name(path)}
    if path.lower().endswith(".exe"):
        aliases.add(_normalize_name(os.path.basename(path)))

    items[key] = {
        "name": clean_name,
        "path": path,
        "type": kind,
        "source": source,
        "aliases": list(aliases - {""}),
    }
    return True


def _resolve_lnk(lnk_path: str) -> str:
    """Разрешить .lnk ярлык через PowerShell."""
    try:
        ps = (
            f'(New-Object -ComObject WScript.Shell)'
            f'.CreateShortcut("{lnk_path}").TargetPath'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=8,
        )
        target = r.stdout.strip()
        if target and os.path.exists(target):
            return target
    except Exception as e:
        log.debug("lnk %s: %s", lnk_path, e)
    return ""


def _scan_shortcuts(items: dict, root: Path) -> None:
    """Сканировать ярлыки .lnk в папке."""
    if not root.exists():
        return
    try:
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if len(items) >= MAX_ITEMS:
                    return
                lower = fname.lower()
                if lower.endswith(".lnk"):
                    lnk = os.path.join(dirpath, fname)
                    target = _resolve_lnk(lnk)
                    if target:
                        name = Path(fname).stem
                        kind = "app" if target.lower().endswith(".exe") else "file"
                        _add_item(items, name, target, kind, "shortcut")
                elif lower.endswith(".exe"):
                    full = os.path.join(dirpath, fname)
                    _add_item(items, Path(fname).stem, full, "app", "start_menu")
    except PermissionError:
        pass


def _scan_registry_uninstall(items: dict) -> None:
    """Установленные программы из реестра."""
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, subkey in roots:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    if len(items) >= MAX_ITEMS:
                        return
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_name) as app_key:
                            display_name = _read_reg(app_key, "DisplayName")
                            if not display_name:
                                continue
                            # Путь к exe
                            path = _read_reg(app_key, "DisplayIcon")
                            if path:
                                path = path.split(",")[0].strip('"')
                            if not path or not os.path.exists(path):
                                install_loc = _read_reg(app_key, "InstallLocation")
                                if install_loc:
                                    for exe in Path(install_loc).glob("*.exe"):
                                        path = str(exe)
                                        break
                            if path and os.path.exists(path):
                                _add_item(items, display_name, path, "app", "registry")
                    except OSError:
                        continue
        except OSError:
            continue


def _read_reg(key, name: str) -> str:
    try:
        val, _ = winreg.QueryValueEx(key, name)
        return str(val) if val else ""
    except OSError:
        return ""


def _scan_app_paths(items: dict) -> None:
    """App Paths в реестре."""
    subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    if len(items) >= MAX_ITEMS:
                        return
                    try:
                        exe_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, exe_name) as app_key:
                            path, _ = winreg.QueryValueEx(app_key, "")
                            if path and os.path.exists(path):
                                name = Path(exe_name).stem
                                _add_item(items, name, path, "app", "app_paths")
                    except OSError:
                        continue
        except OSError:
            continue


def _scan_program_files(items: dict) -> None:
    """Поиск .exe в Program Files (ограниченная глубина)."""
    bases = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    ]
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        _walk_exe(items, Path(base), 0, "program_files")


def _walk_exe(items: dict, root: Path, depth: int, source: str) -> None:
    if depth > MAX_EXE_DEPTH or len(items) >= MAX_ITEMS:
        return
    try:
        for entry in root.iterdir():
            if len(items) >= MAX_ITEMS:
                return
            if entry.is_dir():
                if entry.name.lower() in SKIP_DIRS:
                    continue
                _walk_exe(items, entry, depth + 1, source)
            elif entry.suffix.lower() == ".exe":
                _add_item(items, entry.stem, str(entry), "app", source)
    except PermissionError:
        pass


def _scan_user_folders(items: dict) -> None:
    """Папки пользователя: Desktop, Documents, Downloads (поверхностно)."""
    home = Path.home()
    folders = [
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Downloads", home / "Downloads"),
    ]
    for label, folder in folders:
        if not folder.exists():
            continue
        _walk_user_files(items, folder, 0, label.lower())


def _walk_user_files(items: dict, root: Path, depth: int, source: str) -> None:
    if depth > MAX_FILE_DEPTH or len(items) >= MAX_ITEMS:
        return
    exts = {".exe", ".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md",
            ".py", ".js", ".html", ".lnk", ".url", ".mp4", ".mkv", ".avi",
            ".mov", ".wmv", ".webm", ".mp3", ".wav", ".flac", ".ogg", ".m4a",
            ".zip", ".json", ".csv", ".log"}
    try:
        for entry in root.iterdir():
            if len(items) >= MAX_ITEMS:
                return
            if entry.is_dir():
                if entry.name.lower() not in SKIP_DIRS and not entry.name.startswith("."):
                    _walk_user_files(items, entry, depth + 1, source)
            else:
                if entry.suffix.lower() == ".lnk":
                    target = _resolve_lnk(str(entry))
                    if target:
                        _add_item(items, entry.stem, target,
                                  "app" if target.endswith(".exe") else "file", source)
                elif entry.suffix.lower() in exts:
                    kind = "app" if entry.suffix.lower() == ".exe" else "file"
                    _add_item(items, entry.stem, str(entry), kind, source)
    except PermissionError:
        pass


def _scan_steam_games(items: dict) -> None:
    """Добавить игры Steam."""
    try:
        from skills.steam_control import _parse_games
        for game in _parse_games():
            appid = game["appid"]
            name = game["name"]
            uri = f"steam://rungameid/{appid}"
            key = uri.lower()
            if key not in items and len(items) < MAX_ITEMS:
                items[key] = {
                    "name": name,
                    "path": uri,
                    "type": "game",
                    "source": "steam",
                    "aliases": [_normalize_name(name)],
                }
    except Exception as e:
        log.debug("steam scan: %s", e)


def _scan_path_env(items: dict) -> None:
    """Exe из PATH."""
    path_env = os.environ.get("PATH", "")
    for directory in path_env.split(os.pathsep):
        if not directory or not os.path.isdir(directory):
            continue
        try:
            for fname in os.listdir(directory):
                if len(items) >= MAX_ITEMS:
                    return
                if fname.lower().endswith(".exe"):
                    full = os.path.join(directory, fname)
                    _add_item(items, Path(fname).stem, full, "app", "path")
        except PermissionError:
            continue


def scan_all(force: bool = False, on_progress=None) -> dict:
    """
    Полное сканирование системы.
    Возвращает метаданные индекса.
    """
    global _index_cache, _scanning

    if _scanning and not force:
        return get_index_meta()

    with INDEX_LOCK:
        _scanning = True
        start = time.time()
        items: dict = {}

        if on_progress:
            on_progress("Ярлыки меню Пуск...")
        _scan_shortcuts(items, Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs")
        _scan_shortcuts(items, Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"))

        if on_progress:
            on_progress("Реестр Windows...")
        _scan_registry_uninstall(items)
        _scan_app_paths(items)

        if on_progress:
            on_progress("Program Files...")
        _scan_program_files(items)

        if on_progress:
            on_progress("Папки пользователя...")
        _scan_user_folders(items)

        if on_progress:
            on_progress("Steam и PATH...")
        _scan_steam_games(items)
        _scan_path_env(items)

        # Системные утилиты
        for sys_app in ("notepad.exe", "calc.exe", "mspaint.exe", "explorer.exe",
                        "cmd.exe", "powershell.exe"):
            _add_item(items, Path(sys_app).stem, sys_app, "app", "system")

        index_list = list(items.values())
        meta = {
            "scanned_at": datetime.now().isoformat(),
            "count": len(index_list),
            "duration_sec": round(time.time() - start, 1),
            "items": index_list,
        }

        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        _index_cache = index_list
        _scanning = False
        log.info("Сканирование завершено: %d элементов за %.1f сек",
                 len(index_list), meta["duration_sec"])
        return meta


def load_index() -> list[dict]:
    """Загрузить индекс из файла или кеша."""
    global _index_cache
    if _index_cache is not None:
        return _index_cache

    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _index_cache = data.get("items", [])
            return _index_cache
        except (json.JSONDecodeError, OSError) as e:
            log.error("load_index: %s", e)

    return []


def get_index_meta() -> dict:
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "scanned_at": data.get("scanned_at"),
                "count": data.get("count", 0),
                "duration_sec": data.get("duration_sec"),
            }
        except (json.JSONDecodeError, OSError):
            pass
    return {"count": 0}


def is_scanning() -> bool:
    return _scanning


def should_rescan() -> bool:
    """Нужно ли пересканировать (пустой или устаревший индекс)."""
    meta = get_index_meta()
    if meta.get("count", 0) < 50:
        return True
    scanned_at = meta.get("scanned_at")
    if not scanned_at:
        return True
    try:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(scanned_at)
        return datetime.now() - dt > timedelta(hours=24)
    except ValueError:
        return True


def scan_in_background(force: bool = False) -> None:
    """Запустить сканирование в фоновом потоке."""
    def _run():
        if force or should_rescan():
            scan_all(force=force)
    threading.Thread(target=_run, daemon=True).start()


def _build_search_list(items: list[dict]) -> list[tuple[str, dict]]:
    """Плоский список для fuzzy search: (search_key, item)."""
    entries: list[tuple[str, dict]] = []
    for item in items:
        entries.append((item["name"].lower(), item))
        for alias in item.get("aliases", []):
            if alias:
                entries.append((alias.lower(), item))
    return entries


def search(query: str, limit: int = 5, kind: str | None = None) -> list[tuple[dict, int]]:
    """Нечёткий поиск по индексу. kind: app|file|game|video|audio."""
    items = load_index()
    if not items:
        return []

    query = query.lower().strip()
    if not query:
        return []

    query_words = [w for w in re.split(r"\s+", query) if len(w) >= 3]

    if kind:
        filtered = []
        for item in items:
            path = item.get("path", "").lower()
            ext = Path(path).suffix.lower()
            t = item.get("type", "")
            if kind == "app" and (t == "app" or path.endswith(".exe")):
                filtered.append(item)
            elif kind == "game" and t == "game":
                filtered.append(item)
            elif kind == "video" and ext in {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"}:
                filtered.append(item)
            elif kind == "audio" and ext in {".mp3", ".wav", ".flac", ".ogg", ".m4a"}:
                filtered.append(item)
            elif kind == "file" and t == "file":
                filtered.append(item)
        items = filtered or items

    entries = _build_search_list(items)
    names = [e[0] for e in entries]
    results = process.extract(query, names, scorer=fuzz.WRatio, limit=limit * 3)

    seen: set[str] = set()
    output: list[tuple[dict, int]] = []
    for name, score, idx in results:
        if score < 55:
            continue
        item = entries[idx][1]
        item_name = item["name"].lower()

        # Отсечь мусор: «yandex music» → «ex»
        if len(query) >= 6 and len(item_name) <= 4:
            continue
        if len(query_words) >= 2:
            overlap = sum(
                1 for w in query_words
                if w in item_name or fuzz.partial_ratio(w, item_name) >= 82
            )
            if overlap < 1:
                continue
        if len(query) >= 8 and score < 75:
            continue

        path_key = item["path"].lower()
        if path_key in seen:
            continue
        seen.add(path_key)
        output.append((item, score))
        if len(output) >= limit:
            break
    return output


def launch_item(item: dict) -> str:
    """Запустить найденный элемент."""
    path = item["path"]
    name = item["name"]
    kind = item.get("type", "app")

    try:
        if path.startswith("steam://"):
            os.startfile(path)
        elif kind == "app" or path.lower().endswith(".exe"):
            if os.path.basename(path).lower() in ("explorer.exe", "cmd.exe", "powershell.exe"):
                subprocess.Popen(path, shell=True)
            else:
                os.startfile(path)
        else:
            os.startfile(path)
        return f"Открываю {name}."
    except Exception as e:
        log.error("launch_item %s: %s", path, e)
        return f"Не удалось открыть {name}."


def search_and_launch(query: str) -> str:
    """Найти и запустить по запросу."""
    if not query.strip():
        return "Не указано, что открыть."

    # Если индекс пуст — запустить скан
    if not load_index():
        log.info("Индекс пуст, запускаю сканирование...")
        scan_all()

    matches = search(query, limit=1)
    if matches:
        item, score = matches[0]
        log.info("Найдено '%s' → %s (score %d)", query, item["name"], score)
        return launch_item(item)

    return f"«{query}» не найдено на компьютере. Попробуйте переформулировать."
