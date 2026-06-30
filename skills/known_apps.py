"""Известные приложения: прямые пути, ярлыки, веб-fallback."""

import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from config.settings import log

# canonical → конфиг
# ВАЖНО: одноэлементный кортеж пишется с запятой — ("spotify",), иначе это строка.
KNOWN: dict[str, dict] = {
    "yandex music": {
        "aliases": (
            "яндекс музыка", "яндекс музыку", "yandex music", "яндекс мьюзик",
            "музыка яндекс", "яндексмузыка",
        ),
        "exe_names": ("яндекс музыка.exe", "yandexmusic.exe", "yandex music.exe"),
        "path_hints": ("yandexmusic", "yandex music", "яндекс музыка"),
        "web": "https://music.yandex.ru",
    },
    "spotify": {
        "aliases": (
            "spotify", "спотифай", "спотифи", "споти", "спотифа",
            "спать и фай", "спатифай", "спути фай", "спатьифай",
        ),
        "exe_names": ("spotify.exe",),
        "path_hints": ("spotify",),
        "web": "https://open.spotify.com",
    },
    "steam": {
        "aliases": ("steam", "стим", "стима", "сти"),
        "exe_names": ("steam.exe",),
        "path_hints": ("steam",),
    },
    "telegram": {
        "aliases": ("telegram", "телеграм", "телега"),
        "exe_names": ("telegram.exe",),
        "path_hints": ("telegram",),
    },
    "discord": {
        "aliases": ("discord", "дискорд"),
        "exe_names": ("discord.exe",),
        "path_hints": ("discord",),
    },
    "chrome": {
        "aliases": ("chrome", "хром", "google chrome", "гугл хром"),
        "exe_names": ("chrome.exe",),
        "path_hints": ("google\\chrome",),
    },
    "firefox": {
        "aliases": ("firefox", "файрфокс"),
        "exe_names": ("firefox.exe",),
        "path_hints": ("mozilla firefox",),
    },
    "edge": {
        "aliases": ("edge", "эдж", "microsoft edge"),
        "exe_names": ("msedge.exe",),
        "path_hints": ("microsoft\\edge",),
    },
}


def _as_tuple(value) -> tuple[str, ...]:
    """Строка → кортеж из одного элемента (иначе for hint in 'spotify' идёт по буквам)."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def resolve_canonical(query: str) -> Optional[str]:
    from rapidfuzz import fuzz

    q = query.lower().strip()
    if not q:
        return None

    for canonical, info in KNOWN.items():
        if canonical in q:
            return canonical
        for alias in _as_tuple(info.get("aliases")):
            if alias in q or q in alias:
                return canonical
            if len(alias) >= 5 and fuzz.partial_ratio(alias, q) >= 85:
                return canonical

    # STT часто путает: «спать и фай» → spotify
    spotify_hints = ("спот", "спати", "spoti", "спать и", "спути")
    if any(h in q for h in spotify_hints) and "firefox" not in q and "файр" not in q:
        return "spotify"

    return None


def _find_from_index(canonical: str) -> Optional[str]:
    """Быстрый поиск по уже просканированному индексу ПК."""
    try:
        from skills import system_indexer

        for item, score in system_indexer.search(canonical, limit=3, kind="app"):
            if score < 70:
                continue
            name = item.get("name", "").lower()
            if canonical in name or canonical.replace(" ", "") in name.replace(" ", ""):
                path = item.get("path", "")
                if path and (path.startswith("steam://") or os.path.exists(path)):
                    return path
    except Exception as e:
        log.debug("index lookup %s: %s", canonical, e)
    return None


def _score_exe(path: Path, canonical: str, info: dict) -> tuple:
    name = path.name.lower()
    path_s = str(path).lower()
    exe_names = {n.lower() for n in _as_tuple(info.get("exe_names"))}
    canonical_compact = canonical.replace(" ", "")
    return (
        name not in exe_names,
        "update" in name or "uninst" in name or "installer" in name,
        canonical_compact not in path_s.replace(" ", ""),
        len(path_s),
    )


def _find_exe(canonical: str) -> Optional[str]:
    info = KNOWN[canonical]

    indexed = _find_from_index(canonical)
    if indexed:
        return indexed

    candidates: list[Path] = []
    bases = [
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path(os.environ.get("APPDATA", "")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ]

    # Сначала точные имена exe — быстрее и надёжнее полного rglob
    for name in _as_tuple(info.get("exe_names")):
        for base in bases:
            if not base.exists():
                continue
            try:
                for p in base.rglob(name):
                    candidates.append(p)
            except (PermissionError, OSError):
                continue

    for base in bases:
        if not base.exists():
            continue
        for hint in _as_tuple(info.get("path_hints")):
            if len(hint) < 3:
                continue
            try:
                for p in base.rglob("*.exe"):
                    path_s = str(p).lower()
                    if hint in path_s and hint not in path_s[-4:]:
                        candidates.append(p)
            except (PermissionError, OSError):
                continue

    # Ярлыки в меню Пуск
    start_dirs = [
        Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
    ]
    search_terms = {canonical, *_as_tuple(info.get("aliases"))}
    for sdir in start_dirs:
        if not sdir.exists():
            continue
        try:
            for lnk in sdir.rglob("*.lnk"):
                stem = lnk.stem.lower()
                if not any(term in stem or stem in term for term in search_terms):
                    continue
                target = _resolve_lnk(str(lnk))
                if target:
                    return target
        except (PermissionError, OSError):
            continue

    if candidates:
        seen: set[str] = set()
        unique: list[Path] = []
        for p in candidates:
            key = str(p).lower()
            if key not in seen:
                seen.add(key)
                unique.append(p)
        unique.sort(key=lambda p: _score_exe(p, canonical, info))
        return str(unique[0])

    return None


def _resolve_lnk(lnk_path: str) -> Optional[str]:
    try:
        ps = (
            f'(New-Object -ComObject WScript.Shell)'
            f'.CreateShortcut("{lnk_path}").TargetPath'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
        )
        target = r.stdout.strip()
        if target and os.path.exists(target):
            return target
    except Exception as e:
        log.debug("lnk %s: %s", lnk_path, e)
    return None


def try_launch(query: str) -> Optional[str]:
    """
    Запустить известное приложение напрямую.
    Возвращает сообщение или None если неизвестно.
    """
    canonical = resolve_canonical(query)
    if not canonical:
        return None

    info = KNOWN[canonical]
    exe = _find_exe(canonical)
    if exe:
        try:
            os.startfile(exe)
            log.info("Known app '%s' → %s", canonical, exe)
            return f"Открываю {canonical}."
        except Exception as e:
            log.error("known app launch %s: %s", exe, e)

    web = info.get("web")
    if web:
        webbrowser.open(web)
        log.info("Known app '%s' → web %s", canonical, web)
        return f"Открываю {canonical} в браузере."

    return f"«{canonical}» не найдено на компьютере. Установите приложение или скажите другое."
