"""Small, bounded async wrapper around Google's official Gemini SDK."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from google import genai
from google.genai import types

from .personality import KIKI_PERSONALITY
from .settings import GEMINI_MAX_OUTPUT_TOKENS, GEMINI_MAX_RETRIES, GEMINI_MODEL

logger = logging.getLogger("discord_bot.gemini")
TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
TRANSIENT_ERROR_NAMES = {
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "RemoteProtocolError",
    "TimeoutError",
}


@dataclass(frozen=True)
class ChatTurn:
    """One temporary message included in a channel's short context window."""

    role: Literal["user", "model"]
    author: str
    text: str


def _is_transient_error(error: Exception) -> bool:
    for attribute in ("status_code", "code", "status"):
        value = getattr(error, attribute, None)
        if value is None:
            continue
        try:
            if int(value) in TRANSIENT_HTTP_STATUSES:
                return True
        except (TypeError, ValueError):
            if str(value).upper() in {
                "RESOURCE_EXHAUSTED",
                "UNAVAILABLE",
                "DEADLINE_EXCEEDED",
                "INTERNAL",
            }:
                return True

    return isinstance(error, (TimeoutError, ConnectionError)) or (
        type(error).__name__ in TRANSIENT_ERROR_NAMES
    )


def _safe_http_status(error: Exception) -> int | None:
    """Return only a numeric HTTP status; never expose provider error text."""
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        try:
            status = int(value)
        except (TypeError, ValueError):
            continue
        if 400 <= status <= 599:
            return status
    return None


class GeminiResponder:
    """Generates Kiki's replies without logging prompts or credentials."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def close(self) -> None:
        await self._client.aio.aclose()

    async def generate_reply(
        self,
        turns: list[ChatTurn],
        *,
        mood_context: str = "",
        allow_silence: bool = False,
    ) -> str | None:
        contents = [
            types.Content(
                role=turn.role,
                parts=[
                    types.Part.from_text(
                        text=f"{turn.author}: {turn.text}" if turn.role == "user" else turn.text
                    )
                ],
            )
            for turn in turns
        ]
        system_instruction = KIKI_PERSONALITY
        if mood_context:
            system_instruction += f"\n\nESTADO ATUAL:\n{mood_context}"
        if allow_silence:
            system_instruction += (
                "\n\nESTA É UMA OPORTUNIDADE ESPONTÂNEA. Se não houver uma "
                "contribuição realmente relevante, responda exatamente [[SILENT]]."
            )
        request_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.9,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        )

        for attempt in range(GEMINI_MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=request_config,
                )
                text = response.text
                if not text or not text.strip():
                    return None
                text = text.strip()
                if text.casefold() == "[[silent]]":
                    return None
                return text
            except Exception as error:
                if _is_transient_error(error) and attempt < GEMINI_MAX_RETRIES:
                    delay = min(2**attempt, 4)
                    logger.warning(
                        "Gemini request had a temporary failure; retrying in %s second(s).",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Do not log the exception body: provider errors can contain request details.
                status = _safe_http_status(error)
                logger.warning(
                    "Gemini request failed; skipping this reply (%s%s).",
                    type(error).__name__,
                    f", HTTP {status}" if status is not None else "",
                )
                return None

        return None
