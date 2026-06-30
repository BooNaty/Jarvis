"""Загрузка настроек, путей и логирование."""

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Корневая директория проекта
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_DIR = BASE_DIR / "config"
INTERVIEW_DISCLAIMER_FLAG = CONFIG_DIR / ".interview_disclaimer_ok"
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"
SOUNDS_DIR = ASSETS_DIR / "sounds"
CACHE_DIR = BASE_DIR / "cache" / "tts"
ENV_PATH = BASE_DIR / ".env"
APPS_REGISTRY_PATH = CONFIG_DIR / "apps_registry.json"
INTERVIEW_PROFILE_PATH = CONFIG_DIR / "interview_profile.json"
INTERVIEW_HISTORY_PATH = LOGS_DIR / "interview_history.json"
HISTORY_PATH = LOGS_DIR / "history.json"
LAST_CODE_PATH = LOGS_DIR / "last_code.py"
CRASHES_LOG = LOGS_DIR / "crashes.log"
SETUP_FLAG = CONFIG_DIR / ".setup_complete"

# Создаём необходимые директории
for _dir in (LOGS_DIR, CACHE_DIR, SOUNDS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

load_dotenv(ENV_PATH)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class Settings:
    """Глобальные настройки приложения."""

    def __init__(self) -> None:
        self.reload_from_env()

    def reload_from_env(self) -> None:
        self.anthropic_api_key = _env("ANTHROPIC_API_KEY")
        self.groq_api_key = _env("GROQ_API_KEY")
        self.wake_word = _env("WAKE_WORD", "jarvis")
        self.stt_language = _env("STT_LANGUAGE", "ru-RU")
        self.tts_voice = _env("TTS_VOICE", "ru-RU-DmitryNeural")
        self.steam_path = _env("STEAM_PATH", "auto")
        self.overlay_position = _env("OVERLAY_POSITION", "bottom-right")
        self.autostart = _env("AUTOSTART", "true").lower() in ("true", "1", "yes")
        self.user_title = _env("USER_TITLE", "мисс")

        self.coding_provider = _env("CODING_PROVIDER", "ollama")
        self.interview_provider = _env("INTERVIEW_PROVIDER", "groq")
        self.intent_provider = _env("INTENT_PROVIDER", "groq")

        self.ollama_base_url = _env("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.ollama_model = _env("OLLAMA_MODEL", "qwen2.5-coder:7b")
        self.ollama_coding_model = _env("OLLAMA_CODING_MODEL", "") or self.ollama_model

        self.groq_base_url = _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        self.groq_model = _env("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.groq_interview_model = _env("GROQ_INTERVIEW_MODEL", "") or self.groq_model
        self.groq_intent_model = _env("GROQ_INTENT_MODEL", "llama-3.1-8b-instant")

        self.claude_model = _env("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.intent_max_tokens = 300
        self.coding_max_tokens = 2000
        self.interview_max_tokens = 700
        self.interview_model = _env("INTERVIEW_MODEL", "claude-sonnet-4-6")

        self.tts_rate = "-10%"
        self.tts_pitch = "-4Hz"
        self.tts_volume = "+0%"

        self.silence_threshold = 500
        self.silence_duration = 2.2
        self.max_record_seconds = 18.0
        self.min_record_seconds = 1.0
        self.interview_silence_duration = 0.6
        self.interview_max_record = 12.0
        self.confirm_timeout = 5.0
        self.watchdog_interval = 30


settings = Settings()


def reload_settings() -> None:
    """Перечитать .env после сохранения настроек."""
    load_dotenv(ENV_PATH, override=True)
    settings.reload_from_env()


def setup_logging() -> logging.Logger:
    """Настройка логгера с записью в файл и консоль."""
    logger = logging.getLogger("jarvis")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOGS_DIR / "jarvis.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(fmt)
        logger.addHandler(console)

    return logger


log = setup_logging()


def load_apps_registry() -> dict:
    """Загрузить реестр приложений."""
    if APPS_REGISTRY_PATH.exists():
        with open(APPS_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_apps_registry(registry: dict) -> None:
    """Сохранить реестр приложений."""
    with open(APPS_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def save_env_value(key: str, value: str) -> None:
    """Обновить значение в .env файле."""
    lines: list[str] = []
    found = False
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value
    attr = _env_key_to_attr(key)
    if hasattr(settings, attr):
        setattr(settings, attr, value)


def _env_key_to_attr(key: str) -> str:
    """ANTHROPIC_API_KEY → anthropic_api_key"""
    return key.lower()


def is_setup_complete() -> bool:
    return SETUP_FLAG.exists()


def mark_setup_complete() -> None:
    SETUP_FLAG.touch()


def save_history_entry(command: str, response: str) -> None:
    """Сохранить команду в историю."""
    history: list = []
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = []

    from datetime import datetime

    history.append({
        "time": datetime.now().isoformat(),
        "command": command,
        "response": response,
    })
    # Храним последние 500 записей
    history = history[-500:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def save_interview_entry(
    question: str, answer: str, language: str = "ru", from_call: bool = False
) -> None:
    """История вопросов/ответов собеседования."""
    history: list = []
    if INTERVIEW_HISTORY_PATH.exists():
        try:
            with open(INTERVIEW_HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = []

    from datetime import datetime

    history.append({
        "time": datetime.now().isoformat(),
        "question": question,
        "answer": answer[:2000],
        "language": language,
        "from_call": from_call,
    })
    history = history[-300:]
    with open(INTERVIEW_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
