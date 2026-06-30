"""LLM-бэкенды: Ollama (локально), Groq (облако), Anthropic (опционально)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

import anthropic
import requests
from openai import OpenAI

from config.settings import log, settings


class LLMBackend(ABC):
    name: str

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int,
        model: Optional[str] = None,
    ) -> str:
        ...

    @abstractmethod
    def stream(
        self,
        system: str,
        user: str,
        max_tokens: int,
        model: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        ...


class OpenAICompatibleBackend(LLMBackend):
    """Ollama и Groq — OpenAI-совместимый chat API."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout: float = 60.0,
    ):
        self.name = name
        self.default_model = default_model
        self._client = OpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key or "unused",
            timeout=timeout,
        )

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int,
        model: Optional[str] = None,
    ) -> str:
        model = model or self.default_model
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    def stream(
        self,
        system: str,
        user: str,
        max_tokens: int,
        model: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        model = model or self.default_model
        full_text = ""
        stream = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
            stream=True,
        )
        for chunk in stream:
            piece = chunk.choices[0].delta.content or ""
            if not piece:
                continue
            full_text += piece
            if on_chunk:
                on_chunk(piece)
        return full_text.strip()


class AnthropicBackend(LLMBackend):
    def __init__(self, default_model: str):
        self.name = "anthropic"
        self.default_model = default_model
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY не задан")
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int,
        model: Optional[str] = None,
    ) -> str:
        model = model or self.default_model
        message = self._get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text.strip()

    def stream(
        self,
        system: str,
        user: str,
        max_tokens: int,
        model: Optional[str] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        model = model or self.default_model
        full_text = ""
        with self._get_client().messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                if on_chunk:
                    on_chunk(text)
        return full_text.strip()


def _build_backend(provider: str, task: str) -> LLMBackend:
    provider = (provider or "").lower().strip()

    if provider == "ollama":
        model = settings.ollama_coding_model if task == "coding" else settings.ollama_model
        return OpenAICompatibleBackend(
            name="ollama",
            base_url=settings.ollama_base_url,
            api_key="ollama",
            default_model=model,
            timeout=180.0,
        )

    if provider == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY не задан — получите на console.groq.com")
        if task == "interview":
            model = settings.groq_interview_model
        elif task == "intent":
            model = settings.groq_intent_model
        else:
            model = settings.groq_model
        return OpenAICompatibleBackend(
            name="groq",
            base_url=settings.groq_base_url,
            api_key=settings.groq_api_key,
            default_model=model,
            timeout=45.0,
        )

    if provider == "anthropic":
        if task == "interview":
            model = settings.interview_model
        else:
            model = settings.claude_model
        return AnthropicBackend(default_model=model)

    raise ValueError(f"Неизвестный LLM_PROVIDER: {provider}")


def get_backend(task: str) -> LLMBackend:
    """task: coding | interview | intent"""
    if task == "coding":
        provider = settings.coding_provider
    elif task == "interview":
        provider = settings.interview_provider
    else:
        provider = settings.intent_provider
    return _build_backend(provider, task)


def ollama_is_running() -> bool:
    """Проверка, запущен ли Ollama."""
    base = settings.ollama_base_url.rstrip("/").removesuffix("/v1")
    try:
        r = requests.get(f"{base}/api/tags", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


def log_provider_status() -> None:
    """Статус провайдеров при старте."""
    log.info(
        "LLM: код → %s (%s), собесы → %s (%s), интенты → %s",
        settings.coding_provider,
        settings.ollama_coding_model if settings.coding_provider == "ollama" else settings.groq_model,
        settings.interview_provider,
        settings.groq_interview_model if settings.interview_provider == "groq" else settings.interview_model,
        settings.intent_provider,
    )
    if settings.coding_provider == "ollama":
        if ollama_is_running():
            log.info("Ollama: доступен (%s)", settings.ollama_base_url)
        else:
            log.warning(
                "Ollama: не отвечает на %s — запустите Ollama и: ollama pull %s",
                settings.ollama_base_url,
                settings.ollama_coding_model,
            )
    if settings.interview_provider == "groq" or settings.intent_provider == "groq":
        if settings.groq_api_key:
            log.info("Groq: ключ задан")
        else:
            log.warning("Groq: GROQ_API_KEY не задан — console.groq.com")
