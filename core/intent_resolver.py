"""Выбор интента: быстрые локальные команды vs Groq с подстраховкой."""

from __future__ import annotations

from config.settings import log, settings
from core.brain import Brain, IntentResult
from core.local_intent import OPEN_RE, parse_local_intent

# Только локально — без задержки Groq
_LOCAL_ONLY = frozenset({
    "volume_up", "volume_down", "volume_set", "mute",
    "brightness_up", "brightness_down", "brightness_set",
    "shutdown", "restart", "sleep", "cancel_shutdown",
    "screenshot", "clipboard", "sysinfo",
    "media_play", "media_pause", "media_next", "media_prev", "media_stop",
    "open_steam", "timer", "reminder",
})

# Groq — когда смысл неочевиден
_LLM_PREFERRED = frozenset({
    "coding_help", "find_local", "search_web", "youtube",
    "launch_game", "open_folder", "open_file", "read_file",
    "find_in_folder", "play_media", "unknown",
})


def extract_app_target(command: str) -> str:
    """Извлечь цель «открой X» из текста команды."""
    from skills.known_apps import resolve_canonical

    canonical = resolve_canonical(command)
    if canonical:
        return canonical

    m = OPEN_RE.search(command)
    if m:
        rest = command[m.end() :].strip()
        if len(rest) >= 3:
            from core.local_intent import _resolve_app_name

            return _resolve_app_name(rest) or rest

    from core.local_intent import _resolve_app_name

    return _resolve_app_name(command) or ""


def merge_llm_intent(
    local: IntentResult | None,
    llm: IntentResult,
    command: str,
) -> IntentResult:
    """Groq + локальный разбор: не терять app_name и query."""
    title = settings.user_title

    if llm.intent == "open_app":
        app = (llm.params.get("app_name") or "").strip()
        if not app and local and local.params.get("app_name"):
            app = str(local.params["app_name"]).strip()
        if not app:
            app = extract_app_target(command)
        llm.params["app_name"] = app
        if not app:
            llm.intent = "unknown"
            llm.response = (
                f"Прошу прощения, {title}, не расслышал, что открыть. "
                f"Повторите, пожалуйста."
            )

    elif llm.intent == "close_app":
        app = (llm.params.get("app_name") or "").strip()
        if not app and local and local.params.get("app_name"):
            app = str(local.params["app_name"]).strip()
        if not app:
            app = extract_app_target(command)
        llm.params["app_name"] = app

    elif llm.intent == "unknown" and local is not None:
        return local

    return llm


def resolve_intent(brain: Brain, command: str) -> IntentResult:
    """
    1. Громкость/яркость — мгновенно локально.
    2. Известное приложение (Spotify, Steam…) — локально, без Groq.
    3. Код, поиск, неясные фразы — Groq с подстраховкой params.
    """
    local = parse_local_intent(command)
    if local is not None:
        log.info("Локальный интент: %s %s", local.intent, local.params)

    if local and local.intent in _LOCAL_ONLY:
        return local

    if local and local.intent == "coding_help":
        return local

    # Быстрый путь: локально уже есть цель — Groq только портит params
    if local and local.intent == "open_app":
        app = str(local.params.get("app_name", "")).strip()
        if app and len(app) >= 3 and app.lower() not in (
            "открой", "открыть", "запусти", "open", "launch",
        ):
            log.info("Быстрый open_app: %s (без Groq)", app)
            return local

    if local and local.intent == "open_browser":
        return local

    need_llm = (
        local is None
        or local.intent in _LLM_PREFERRED
        or local.intent in ("open_app", "close_app")
    )

    if not need_llm and local is not None:
        return local

    llm = brain.parse_intent(command)
    merged = merge_llm_intent(local, llm, command)
    if merged.intent != "unknown":
        log.info(
            "ИИ-интент (%s): %s %s",
            settings.intent_provider,
            merged.intent,
            merged.params,
        )
    return merged
