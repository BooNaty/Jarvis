"""Локальное управление ПК: поиск, файлы, медиа-кнопки — без Claude API."""

import os
import re
import subprocess
from pathlib import Path

import keyboard

from config.settings import log
from skills import file_manager, system_indexer

VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma"}
TEXT_EXT = {".txt", ".md", ".py", ".json", ".csv", ".log", ".xml", ".html", ".env", ".ini", ".yaml", ".yml"}
READABLE_MAX = 2500


def _file_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in TEXT_EXT:
        return "text"
    return "file"


def media_play_pause() -> str:
    try:
        keyboard.send("play/pause media")
        return "Воспроизведение."
    except Exception as e:
        log.error("media_play_pause: %s", e)
        return "Не удалось управлять воспроизведением."


def media_next() -> str:
    try:
        keyboard.send("next track")
        return "Следующий трек."
    except Exception as e:
        return "Не удалось переключить трек."


def media_previous() -> str:
    try:
        keyboard.send("previous track")
        return "Предыдущий трек."
    except Exception as e:
        return "Не удалось переключить трек."


def media_stop() -> str:
    try:
        keyboard.send("stop media")
        return "Остановлено."
    except Exception as e:
        return "Не удалось остановить воспроизведение."


def find_on_pc(query: str, limit: int = 3) -> str:
    """Найти файл/приложение на компьютере (индекс)."""
    if not query.strip():
        return "Не указано, что искать."

    if not system_indexer.load_index():
        system_indexer.scan_in_background()

    matches = system_indexer.search(query, limit=limit)
    if not matches:
        return f"«{query}» не найдено. Запустите «Сканировать компьютер» в трее."

    if len(matches) == 1:
        item, score = matches[0]
        return f"Найдено: {item['name']} ({item.get('type', 'file')}). Путь: {item['path']}."

    lines = [f"Найдено {len(matches)} вариантов:"]
    for item, score in matches:
        lines.append(f"— {item['name']} ({score}%)")
    lines.append("Скажите «открой» и название для запуска.")
    return " ".join(lines)


def open_on_pc(query: str, prefer: str | None = None) -> str:
    """Найти и открыть по индексу ПК."""
    if not query.strip():
        return "Не указано, что открыть."

    # Сначала — известные приложения (Яндекс Музыка, Spotify…)
    from skills.known_apps import try_launch

    known_result = try_launch(query)
    if known_result:
        return known_result

    if not system_indexer.load_index():
        log.info("Индекс пуст, запускаю сканирование...")
        system_indexer.scan_all()

    matches = system_indexer.search(query, limit=5)
    if prefer:
        matches = _prefer_kind(matches, prefer)

    if matches:
        item, score = matches[0]
        if score < 85:
            return (
                f"Не уверен, что «{query}» — это «{item['name']}». "
                f"Уточните название, {settings.user_title}."
            )
        log.info("Открываю '%s' → %s (%d)", query, item["name"], score)
        return system_indexer.launch_item(item)

    return f"«{query}» не найдено на компьютере."


def _prefer_kind(matches: list, kind: str) -> list:
    """Отсортировать: видео/аудио/приложения в приоритете."""
    ext_sets = {
        "video": VIDEO_EXT,
        "audio": AUDIO_EXT,
        "text": TEXT_EXT,
        "app": {".exe"},
    }
    target = ext_sets.get(kind, set())

    def score_item(pair: tuple) -> int:
        item, fuzzy = pair
        path = item.get("path", "").lower()
        ext = Path(path).suffix.lower()
        bonus = 30 if ext in target else 0
        if kind == "app" and item.get("type") == "app":
            bonus += 30
        if kind == "video" and ext in VIDEO_EXT:
            bonus += 30
        return fuzzy + bonus

    return sorted(matches, key=score_item, reverse=True)


def find_in_folder(folder_hint: str, query: str) -> str:
    """Поиск файла внутри папки (стандартной или по имени)."""
    folder = _resolve_folder(folder_hint)
    if not folder:
        return f"Папка «{folder_hint}» не найдена."

    query_lower = query.lower().strip()
    found: list[Path] = []
    try:
        for root, dirs, files in os.walk(folder):
            depth = root[len(str(folder)) :].count(os.sep)
            if depth > 4:
                dirs.clear()
                continue
            for fname in files:
                if query_lower in fname.lower():
                    found.append(Path(root) / fname)
                    if len(found) >= 10:
                        break
            if len(found) >= 10:
                break
    except PermissionError:
        return "Нет доступа к папке."

    if not found:
        return f"В «{folder_hint}» не найдено «{query}»."

    if len(found) == 1:
        return open_path(str(found[0]))

    names = ", ".join(p.name for p in found[:5])
    return f"Найдено несколько: {names}. Уточните название."


def open_path(path: str) -> str:
    """Открыть файл или папку по пути."""
    p = Path(path)
    if not p.exists():
        return f"Не найдено: {path}"
    try:
        os.startfile(str(p))
        return f"Открываю {p.name}."
    except Exception as e:
        log.error("open_path: %s", e)
        return f"Не удалось открыть {p.name}."


def play_media(query: str) -> str:
    """Воспроизвести фильм/музыку/файл с диска."""
    result = open_on_pc(query, prefer="video")
    if "не найдено" in result.lower():
        result = open_on_pc(query, prefer="audio")
    return result


def read_local_file(query: str) -> str:
    """Прочитать локальный текстовый файл."""
    matches = system_indexer.search(query, limit=3)
    matches = _prefer_kind(matches, "text")

    if not matches:
        return f"Файл «{query}» не найден."

    path = matches[0][0]["path"]
    ext = Path(path).suffix.lower()
    if ext not in TEXT_EXT and ext != ".pdf":
        return f"«{matches[0][0]['name']}» — не текстовый файл. Скажите «открой» для запуска."

    if ext == ".pdf":
        open_path(path)
        return f"Открываю PDF {matches[0][0]['name']} в просмотрщике."

    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return "Файл пуст."
        if len(text) > READABLE_MAX:
            return f"Начало файла {matches[0][0]['name']}: {text[:READABLE_MAX]}..."
        return f"Файл {matches[0][0]['name']}: {text}"
    except Exception as e:
        log.error("read_local_file: %s", e)
        return f"Не удалось прочитать файл: {e}"


def close_app(query: str) -> str:
    """Закрыть программу или окно."""
    if not query.strip():
        return "Что закрыть?"

    q = query.strip().lower()
    if q in ("окно", "это", "текущее", "window", "this", "программу"):
        try:
            keyboard.send("alt+f4")
            return "Закрываю окно."
        except Exception as e:
            log.error("close window: %s", e)
            return "Не удалось закрыть окно."

    try:
        import pygetwindow as gw

        for w in gw.getAllWindows():
            if not w.title or not w.visible:
                continue
            if q in w.title.lower():
                try:
                    w.close()
                    return f"Закрываю {w.title}."
                except Exception:
                    w.activate()
                    keyboard.send("alt+f4")
                    return f"Закрываю {w.title}."
    except Exception as e:
        log.debug("pygetwindow close: %s", e)

    matches = system_indexer.search(query, limit=1, kind="app")
    if matches:
        item = matches[0][0]
        exe = Path(item["path"]).name
        if exe.lower().endswith(".exe"):
            r = subprocess.run(
                ["taskkill", "/IM", exe, "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                return f"Закрываю {item['name']}."
            return f"«{item['name']}» не запущено."

    return f"«{query}» не найдено среди программ."


def _resolve_folder(hint: str) -> Path | None:
    hint_l = hint.lower().strip()
    if hint_l in file_manager.FOLDERS:
        p = file_manager.FOLDERS[hint_l]
        return p if p.exists() else None

    # Частичное совпадение: «загрузки», «документы»
    for key, path in file_manager.FOLDERS.items():
        if hint_l in key or key in hint_l:
            return path if path.exists() else None

    # Путь
    p = Path(hint)
    if p.exists() and p.is_dir():
        return p

    # Поиск папки в домашней директории
    home = Path.home()
    for item in home.iterdir():
        if item.is_dir() and hint_l in item.name.lower():
            return item
    return None
