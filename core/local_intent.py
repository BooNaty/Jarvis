"""Локальное распознавание команд ПК — без Claude API."""

import re
from typing import Optional

from rapidfuzz import fuzz

from config.settings import log, settings
from core.brain import IntentResult

# --- Глаголы ---
OPEN_VERBS = (
    r"открой|открыть|запусти|запустить|включи|включить|покажи|"
    r"open|launch|run|start|show"
)
FIND_VERBS = r"найди|найти|поищи|поиск|где|find|search|locate"
PLAY_VERBS = r"включи|воспроизведи|поставь|проиграй|play|запусти"

OPEN_RE = re.compile(rf"(?:{OPEN_VERBS})\s+", re.IGNORECASE)
FIND_RE = re.compile(rf"(?:{FIND_VERBS})\s+", re.IGNORECASE)
PLAY_RE = re.compile(rf"(?:{PLAY_VERBS})\s+", re.IGNORECASE)
CLOSE_RE = re.compile(
    r"(?:закрой|закрыть|закройте|выключи|выруби|close|kill)\s+",
    re.IGNORECASE,
)

# Имена из индекса ПК (обновляется при старте)
_index_names: list[str] = []

# Популярные приложения (алиасы → имя для индекса)
APP_ALIASES: dict[str, tuple[str, ...]] = {
    "steam": ("steam", "стим", "стима", "сти", "ste"),
    "spotify": ("spotify", "спотифай", "спотифи", "споти", "пай спать", "спатифай"),
    "yandex music": ("яндекс музыка", "яндекс музыку", "yandex music", "яндекс мьюзик", "музыка яндекс"),
    "chrome": ("chrome", "хром", "гугл хром", "google chrome", "браузер хром"),
    "firefox": ("firefox", "файрфокс", "мозилла"),
    "edge": ("edge", "эдж", "microsoft edge"),
    "telegram": ("telegram", "телеграм", "телега"),
    "discord": ("discord", "дискорд"),
    "vscode": ("vscode", "vs code", "visual studio code", "код"),
    "cursor": ("cursor", "курсор"),
    "notepad": ("notepad", "блокнот", "ноутпад"),
    "calculator": ("calculator", "калькулятор", "calc"),
    "explorer": ("explorer", "проводник", "файлы"),
}

WAKE_WORDS = ("джарвис", "jarvis", "жарвис", "джерри", "дарвис", "гарвис")
WAKE_FUZZY_TARGETS = ("джарвис", "jarvis", "жарвис")
WAKE_FUZZY_MIN_SCORE = 70

CODING_WORDS = (
    "python", "пайтон", "питон", "javascript", "typescript", "java",
    "html", "css", "sql", "react", "flutter", "dart",
)

FOLDER_WORDS = (
    r"загрузки|downloads|документы|documents|рабочий стол|desktop|стол|"
    r"музыка|music|видео|videos|изображения|pictures|фото|"
    r"видеозаписи|downloads|desktop"
)


def _clean(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^\w\s\-]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def _dedupe_words(text: str) -> str:
    seen: list[str] = []
    for word in text.split():
        if word not in seen:
            seen.append(word)
    return " ".join(seen)


def _resp(msg: str) -> str:
    return msg.format(title=settings.user_title)


def _intent(
    name: str, response: str, needs_confirm: bool = False, **params
) -> IntentResult:
    return IntentResult(
        intent=name,
        params=params,
        response=_resp(response),
        needs_confirm=needs_confirm,
    )


def _strip_prefix(text: str, pattern: re.Pattern) -> str:
    m = pattern.search(text)
    if m:
        return text[m.end() :].strip()
    return text.strip()


def refresh_from_index() -> int:
    """Загрузить имена программ из индекса для распознавания команд."""
    global _index_names
    try:
        from skills.system_indexer import load_index

        items = load_index()
        names: set[str] = set()
        for item in items:
            name = item.get("name", "").strip()
            if name:
                names.add(name.lower())
            for alias in item.get("aliases", []):
                if alias:
                    names.add(alias.lower())
        _index_names = sorted(names)
        log.info("Индекс команд: %d имён программ/файлов", len(_index_names))
        return len(_index_names)
    except Exception as e:
        log.error("refresh_from_index: %s", e)
        return 0


def _resolve_app_name(text: str) -> Optional[str]:
    """Сопоставить алиас или имя из индекса → запрос для поиска."""
    t = _clean(text)
    if not t or len(t) < 3:
        return None

    from skills.known_apps import resolve_canonical

    canonical = resolve_canonical(t)
    if canonical:
        return canonical

    for canonical, aliases in APP_ALIASES.items():
        for alias in aliases:
            if len(alias) >= 4 and (alias in t or fuzz.partial_ratio(alias, t) >= 88):
                return canonical

    # Fuzzy по индексу сканирования ПК
    if _index_names:
        from rapidfuzz import process

        match = process.extractOne(t, _index_names, scorer=fuzz.WRatio)
        if match and match[1] >= 86:
            return match[0]

    return None  # без уверенного совпадения — не угадывать (иначе «пайтон» → GWENT)


def _is_steam(name: str) -> bool:
    n = name.lower().strip()
    if n in APP_ALIASES["steam"]:
        return True
    return fuzz.ratio(n, "steam") >= 72 or fuzz.ratio(n, "стим") >= 72


def _is_web_search(text: str) -> bool:
    return bool(re.search(
        r"(в интернете|в гугле|в google|в сети|online|в яндексе|на сайте)",
        text, re.I,
    ))


def _is_local_find(text: str) -> bool:
    return bool(re.search(
        r"(на компьютере|на пк|у меня|на диске|в папке|файл|фильм|песню|песня|документ)",
        text, re.I,
    ))


def parse_local_intent(command: str) -> Optional[IntentResult]:
    """Распознать локальную команду. None → нужен Claude."""
    if not command or not command.strip():
        return None

    raw = command.strip()
    text = _dedupe_words(_clean(raw))

    # ===== Медиа-кнопки (Spotify, Яндекс Музыка, плеер) =====
    if re.search(r"(пауза|pause|стоп музык|останови музык|stop music)", text):
        return _intent("media_pause", "Пауза, {title}.")
    if re.search(r"(продолжи|продолжить|resume|воспроизведи|play music|плей)", text):
        if not PLAY_RE.search(raw):  # не «включи фильм»
            return _intent("media_play", "Воспроизведение, {title}.")
    if re.search(r"(следующ|next track|next song|дальше)", text):
        return _intent("media_next", "Следующий трек, {title}.")
    if re.search(r"(предыдущ|previous track|назад трек)", text):
        return _intent("media_prev", "Предыдущий трек, {title}.")
    if re.search(r"(стоп|stop media|останови воспроизведение)", text):
        return _intent("media_stop", "Остановлено, {title}.")

    # ===== Громкость / яркость / питание =====
    if re.search(r"(громче|погромче|увеличь громкость|volume up)", text):
        m = re.search(r"(\d+)", text)
        return _intent("volume_up", "Сейчас, {title}.", percent=int(m.group(1)) if m else 10)
    if re.search(r"(тише|потише|уменьши громкость|volume down)", text):
        m = re.search(r"(\d+)", text)
        return _intent("volume_down", "Сейчас, {title}.", percent=int(m.group(1)) if m else 10)
    if re.search(r"(без звука|выключи звук|mute|замолчи)", text):
        return _intent("mute", "Выключаю звук, {title}.")
    m = re.search(r"(?:громкость|volume)\s*(\d{1,3})", text)
    if m:
        return _intent("volume_set", "Устанавливаю громкость, {title}.", percent=int(m.group(1)))
    if re.search(r"(яркость выше|ярче|сделай ярче|brightness up|больше яркости)", text):
        return _intent("brightness_up", "Делаю ярче, {title}.")
    if re.search(r"(яркость ниже|темнее|сделай темнее|brightness down|меньше яркости)", text):
        return _intent("brightness_down", "Делаю темнее, {title}.")
    m = re.search(r"яркость\s*(\d{1,3})", text)
    if m:
        return _intent("brightness_set", "Устанавливаю яркость, {title}.", percent=int(m.group(1)))
    if re.search(r"(выключи компьютер|shutdown|выключи пк)", text):
        return _intent("shutdown", "Выключить компьютер, {title}?", needs_confirm=True)
    if re.search(r"(перезагруз|restart|reboot)", text):
        return _intent("restart", "Перезагрузить компьютер, {title}?", needs_confirm=True)
    if re.search(r"(спящий режим|sleep|усыпи)", text):
        return _intent("sleep", "Спящий режим, {title}?", needs_confirm=True)
    if re.search(r"(отмени выключение|cancel shutdown)", text):
        return _intent("cancel_shutdown", "Отменяю, {title}.")

    # ===== Закрыть программу / окно =====
    m = CLOSE_RE.search(raw)
    if m:
        target = _clean(raw[m.end() :])
        if target and not re.search(r"(компьютер|пк|windows|систему)", target):
            app = _resolve_app_name(target) or target
            return _intent("close_app", "Закрываю, {title}.", app_name=app)
    if re.search(r"^(закрой|close)$", text):
        return _intent("close_app", "Закрываю окно, {title}.", app_name="окно")

    # ===== Система =====
    if re.search(r"(скриншот|screenshot|снимок экрана)", text):
        return _intent("screenshot", "Делаю снимок, {title}.")
    if re.search(r"(буфер обмена|clipboard|что в буфере)", text):
        return _intent("clipboard", "Сейчас, {title}.")
    if re.search(r"(система|sysinfo|характеристики|информация о системе)", text):
        return _intent("sysinfo", "Сейчас, {title}.")

    # ===== Прочитать файл =====
    m = re.search(
        r"(?:прочитай|прочти|read|открой и прочитай|что в файле)\s+(?:файл\s+)?(.+)",
        text,
    )
    if m:
        return _intent("read_file", "Читаю файл, {title}.", query=m.group(1).strip())

    # ===== Поиск в папке =====
    m = re.search(
        rf"(?:{FIND_VERBS})\s+(?:в|в папке)\s+({FOLDER_WORDS}|[^\s]+)\s+(.+)",
        text,
    )
    if m:
        return _intent(
            "find_in_folder",
            "Ищу, {title}.",
            folder=m.group(1).strip(),
            query=m.group(2).strip(),
        )

    # ===== Локальный поиск на ПК (по умолчанию для «найди») =====
    if FIND_RE.search(raw):
        q = _strip_prefix(raw, FIND_RE)
        q = re.sub(
            r"^(?:на компьютере|на пк|у меня|файл|фильм|песню|в интернете)\s+",
            "",
            q,
            flags=re.I,
        ).strip()
        if q:
            if _is_web_search(text):
                return _intent("search_web", "Ищу, {title}.", query=q)
            return _intent("find_local", "Ищу на компьютере, {title}.", query=q)
    m = re.search(r"(?:загугли|google)\s+(.+)", text)
    if m:
        return _intent("search_web", "Ищу, {title}.", query=m.group(1).strip())

    # ===== YouTube / погода =====
    m = re.search(r"(?:youtube|ютуб|ютюб)\s+(.+)", text)
    if m:
        return _intent("youtube", "Открываю YouTube, {title}.", query=m.group(1).strip())
    m = re.search(r"погода(?:\s+в\s+(.+))?", text)
    if m:
        return _intent("weather", "Сейчас узнаю, {title}.", city=(m.group(1) or "Москва").strip())

    # ===== Воспроизвести фильм/музыку =====
    m = re.search(
        rf"(?:{PLAY_VERBS})\s+(?:фильм|видео|музыку|песню|трек|movie|video|song)?\s*(.+)",
        text,
    )
    if m:
        q = m.group(1).strip()
        if q and not _is_steam(q):
            return _intent("play_media", "Включаю, {title}.", query=q)

    # ===== Открыть папку =====
    m = re.search(r"(?:открой папку|open folder|папка)\s+(.+)", text)
    if m:
        return _intent("open_folder", "Открываю папку, {title}.", folder=m.group(1).strip())

    # ===== Открыть файл =====
    m = re.search(r"(?:открой файл|open file)\s+(.+)", text)
    if m:
        return _intent("open_file", "Открываю, {title}.", query=m.group(1).strip())

    # ===== Steam =====
    if _is_steam(text) or (
        re.search(r"\b(steam|стим)\b", text) and OPEN_RE.search(raw)
    ):
        return _intent("open_steam", "Открываю Steam, {title}.")

    # ===== Запуск игры Steam =====
    m = re.search(r"(?:запусти игру|launch game|игра)\s+(.+)", text)
    if m:
        return _intent("launch_game", "Запускаю игру, {title}.", game_name=m.group(1).strip())

    # ===== Браузер =====
    if re.search(r"(открой браузер|open browser)$", text):
        return _intent("open_browser", "Открываю браузер, {title}.")

    # ===== Таймер =====
    m = re.search(r"(?:напомни|таймер|reminder|timer)\s+(?:через\s+)?(\d+)\s*(?:минут|мин|minutes?)(?:\s+(.+))?", text)
    if m:
        return _intent(
            "timer",
            "Запомнил, {title}.",
            minutes=int(m.group(1)),
            text=(m.group(2) or "").strip(),
        )

    # ===== Код / Python — не путать с приложениями из индекса =====
    if not OPEN_RE.search(raw) and not CLOSE_RE.search(raw):
        if text in CODING_WORDS or any(w in text.split() for w in CODING_WORDS):
            topic = next((w for w in CODING_WORDS if w in text), text)
            return _intent("coding_help", "Слушаю, {title}.", topic=topic)

    # ===== Открыть приложение (универсально) =====
    m = OPEN_RE.search(raw)
    if m:
        rest = raw[m.end() :].strip()
        if len(rest) < 3:
            return None
        app = _resolve_app_name(rest)
        if app:
            if app == "steam" or _is_steam(app):
                return _intent("open_steam", "Открываю Steam, {title}.")
            if app in ("explorer",):
                return _intent("open_folder", "Открываю, {title}.", folder="рабочий стол")
            return _intent("open_app", "Сейчас открою, {title}.", app_name=app)

    # «steam открой» и т.п.
    if re.search(r"\b(steam|стим)\b", text) and re.search(
        rf"\b(?:{OPEN_VERBS})\b", text, re.I
    ):
        return _intent("open_steam", "Открываю Steam, {title}.")

    # ===== Без глагола: только известные приложения =====
    from skills.known_apps import resolve_canonical

    app = resolve_canonical(text)
    if app and len(text.split()) <= 4:
        if app == "steam" or _is_steam(app):
            return _intent("open_steam", "Открываю Steam, {title}.")
        return _intent("open_app", "Сейчас открою, {title}.", app_name=app)

    return None
