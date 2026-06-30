"""ИИ-мозг: код (Ollama), собесы (Groq), интенты (Groq)."""



import json

import re

from dataclasses import dataclass, field

from typing import Any, Callable, Optional



from config.settings import log, settings

from core.llm_provider import get_backend





INTENT_SYSTEM_PROMPT = """Ты JARVIS — взрослый вежливый голосовой дворецкий в духе фильмов о Железном человеке.

Обращайся к пользователю только на «Вы». Используй «{title}» в конце или начале фразы.

Голосовой стиль ответа (response): спокойный, уверенный, уважительный, без сленга и панибратства.

Как дворецкий: кратко, по делу, с достоинством.



Получаешь голосовую команду на русском языке.



Верни ТОЛЬКО JSON без markdown и без пояснений:



{{

  "intent": "open_app|open_browser|search_web|weather|youtube|volume_set|volume_up|volume_down|mute|brightness_set|shutdown|restart|sleep|cancel_shutdown|open_steam|launch_game|open_folder|screenshot|clipboard|timer|reminder|sysinfo|coding_help|unknown",

  "params": {{}},

  "response": "короткая вежливая фраза вслух, 1-2 предложения, с обращением {title}",

  "needs_confirm": false

}}



Правила:

- Для shutdown, restart, sleep — needs_confirm: true

- params: извлекай числа, названия, пути, запросы

- volume_set: params.percent (0-100)

- volume_up/down: params.percent (по умолчанию 10)

- brightness_set: params.percent или "max"/"min"

- open_app: params.app_name — латиницей: spotify, steam, firefox, chrome, telegram, discord, notepad, calculator, vscode, cursor, edge, yandex music

- «открой спотифай» / «спотифай» → open_app, app_name: "spotify" (НЕ firefox)

- «открой файрфокс» → open_app, app_name: "firefox"

- «открой стим» → open_steam (не open_app)

- Речь может быть с ошибками распознавания — угадывай по смыслу

- search_web: params.query

- weather: params.city

- youtube: params.query

- open_folder: params.folder

- launch_game: params.game_name

- timer/reminder: params.minutes, params.text

- coding_help: для запросов о коде, программировании, объяснении алгоритмов

- unknown: если не понял команду"""





CODING_SYSTEM_PROMPT = """Ты JARVIS — вежливый ИИ-помощник по программированию.

Обращайся к пользователю на «Вы», используй «{title}».

Тон: профессиональный, учтивый, как опытный наставник.



Ответь на запрос пользователя о коде.



Верни ТОЛЬКО JSON без markdown:



{{

  "summary": "краткое резюме для озвучивания, 2-3 предложения, с обращением {title}",

  "code": "полный код или пустая строка если код не нужен",

  "language": "python|javascript|html|css|sql|bash|other"

}}"""





@dataclass

class InterviewResult:

    answer: str = ""

    bullets: str = ""





INTERVIEW_FAST_PROMPT = """You are a silent interview coach helping a job candidate in real time.



Candidate profile:

{context}



CRITICAL: Write the ENTIRE answer in {language}. If language is English — answer ONLY in English. If Russian — ONLY in Russian.



Style: {style_hint}

- First person, natural spoken language (as if candidate is speaking)

- No markdown, no JSON, no labels — plain text only

- Behavioral questions: STAR method (Situation, Task, Action, Result)

- Technical questions: direct answer → details → real example from profile

- Do NOT invent experience not in the profile

- Start answering immediately, be concise but complete"""





@dataclass

class IntentResult:

    intent: str = "unknown"

    params: dict = field(default_factory=dict)

    response: str = ""

    needs_confirm: bool = False





@dataclass

class CodingResult:

    summary: str = ""

    code: str = ""

    language: str = "python"





class Brain:

    """Мульти-провайдер: Ollama (код), Groq (собесы + редкие интенты)."""



    def __init__(self):

        self._title = settings.user_title



    def set_title(self, title: str) -> None:

        self._title = title



    def parse_intent(self, command: str) -> IntentResult:

        """Режим 1: быстрое распознавание интента (Groq)."""

        try:

            backend = get_backend("intent")

            system = INTENT_SYSTEM_PROMPT.format(title=self._title)

            raw = backend.complete(

                system=system,

                user=command,

                max_tokens=settings.intent_max_tokens,

            )

            data = self._parse_json(raw)

            return IntentResult(

                intent=data.get("intent", "unknown"),

                params=data.get("params", {}),

                response=data.get("response", ""),

                needs_confirm=bool(data.get("needs_confirm", False)),

            )

        except Exception as e:

            log.error("Ошибка parse_intent (%s): %s", settings.intent_provider, e)

            return IntentResult(

                intent="unknown",

                response=f"Прошу прощения, {self._title}, не удалось обработать команду.",

            )



    def coding_help(self, command: str) -> CodingResult:

        """Режим 2: полный ответ с кодом (Ollama)."""

        try:

            backend = get_backend("coding")

            system = CODING_SYSTEM_PROMPT.format(title=self._title)

            raw = backend.complete(

                system=system,

                user=command,

                max_tokens=settings.coding_max_tokens,

            )

            data = self._parse_json(raw)

            return CodingResult(

                summary=data.get("summary", ""),

                code=data.get("code", ""),

                language=data.get("language", "python"),

            )

        except Exception as e:

            log.error("Ошибка coding_help (%s): %s", settings.coding_provider, e)

            hint = ""

            if settings.coding_provider == "ollama":

                hint = " Запустите Ollama и выполните: ollama pull qwen2.5-coder:7b"

            return CodingResult(

                summary=(

                    f"Прошу прощения, {self._title}, не удалось получить ответ от ИИ.{hint}"

                ),

            )



    def interview_answer_stream(

        self,

        question: str,

        context: str,

        language: str = "ru",

        style: str = "concise",

        on_chunk: Optional[Callable[[str], None]] = None,

    ) -> str:

        """Стриминговый ответ для собеседования (Groq)."""

        style_hint = (

            "3-4 sentences, to the point"

            if style == "concise"

            else "detailed with examples"

        )

        lang_name = "Russian" if language == "ru" else "English"



        try:

            backend = get_backend("interview")

            system = INTERVIEW_FAST_PROMPT.format(

                context=context,

                language=lang_name,

                style_hint=style_hint,

            )

            return backend.stream(

                system=system,

                user=question,

                max_tokens=settings.interview_max_tokens,

                on_chunk=on_chunk,

            )

        except Exception as e:

            log.error("interview_answer_stream (%s): %s", settings.interview_provider, e)

            if settings.interview_provider == "groq":

                err = (

                    "Не удалось сформировать ответ. Проверьте GROQ_API_KEY в .env."

                    if language == "ru"

                    else "Failed to generate answer. Check GROQ_API_KEY in .env."

                )

            else:

                err = (

                    "Не удалось сформировать ответ. Проверьте настройки ИИ."

                    if language == "ru"

                    else "Failed to generate answer. Check AI settings."

                )

            if on_chunk:

                on_chunk(err)

            return err



    def interview_answer(self, question: str, context: str, language: str = "ru",

                         style: str = "concise") -> InterviewResult:

        """Синхронный ответ (fallback без стриминга)."""

        text = self.interview_answer_stream(question, context, language, style)

        return InterviewResult(answer=text, bullets="")



    @staticmethod

    def _parse_json(raw: str) -> dict[str, Any]:

        """Извлечь JSON из ответа LLM."""

        raw = raw.strip()

        if raw.startswith("```"):

            raw = re.sub(r"^```(?:json)?\s*", "", raw)

            raw = re.sub(r"\s*```$", "", raw)

        try:

            return json.loads(raw)

        except json.JSONDecodeError:

            match = re.search(r"\{.*\}", raw, re.DOTALL)

            if match:

                return json.loads(match.group())

            raise


