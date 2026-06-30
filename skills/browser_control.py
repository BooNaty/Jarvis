"""Управление браузером, поиск, погода, YouTube."""

import json
import urllib.parse
import webbrowser

import requests

from config.settings import log


def search_web(query: str) -> str:
    """Поиск в Google."""
    if not query:
        return "Не указан поисковый запрос."
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return f"Ищу «{query}» в Google."


def open_url(url: str) -> str:
    """Открыть URL или сайт."""
    if not url:
        return "Не указан адрес."
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Открываю {url}."


def search_youtube(query: str) -> str:
    """Поиск на YouTube."""
    if not query:
        return "Не указан запрос."
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return f"Ищу «{query}» на YouTube."


def get_weather(city: str) -> str:
    """Погода через wttr.in API."""
    if not city:
        city = "Moscow"
    try:
        # Транслитерация не нужна — wttr.in понимает кириллицу
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=ru"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "JARVIS/1.0"})
        resp.raise_for_status()
        data = resp.json()

        current = data["current_condition"][0]
        temp = current["temp_C"]
        desc_list = current.get("lang_ru", current.get("weatherDesc", []))
        desc = desc_list[0]["value"] if desc_list else "без описания"
        humidity = current.get("humidity", "?")
        wind = current.get("windspeedKmph", "?")

        return (
            f"В городе {city} сейчас {temp} градусов, {desc}. "
            f"Влажность {humidity} процентов, ветер {wind} километров в час."
        )
    except Exception as e:
        log.error("weather: %s", e)
        return f"Не удалось получить погоду для {city}."


def open_browser() -> str:
    """Открыть браузер по умолчанию."""
    webbrowser.open("https://www.google.com")
    return "Открываю браузер."
