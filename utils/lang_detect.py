"""Определение языка вопроса (ru / en)."""

import re


def detect_language(text: str) -> str:
    """
    Определить язык текста: 'ru' или 'en'.
    Для смешанного текста — по преобладанию букв.
    """
    if not text or not text.strip():
        return "ru"

    cyrillic = len(re.findall(r"[\u0400-\u04FF]", text))
    latin = len(re.findall(r"[a-zA-Z]", text))

    if latin > cyrillic:
        return "en"
    if cyrillic > 0:
        return "ru"
    return "en"


def resolve_interview_language(question: str, profile_lang: str = "auto") -> str:
    """
    Выбрать язык ответа.
    profile_lang: auto | ru | en
    """
    if profile_lang == "auto":
        return detect_language(question)
    return profile_lang if profile_lang in ("ru", "en") else "ru"
