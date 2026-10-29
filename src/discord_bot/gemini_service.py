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


class GeminiResponder:
    """Generates Kiki's replies without logging prompts or credentials."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def close(self) -> None:
        await self._client.aio.aclose()

    async def generate_reply(self, turns: list[ChatTurn]) -> str | None:
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
        request_config = types.GenerateContentConfig(
            system_instruction=KIKI_PERSONALITY,
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
                return text.strip() if text and text.strip() else None
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
                logger.warning(
                    "Gemini request failed; skipping this reply (%s).",
                    type(error).__name__,
                )
                return None

        return None
