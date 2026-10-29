"""Editable behavior and safety limits for Kiki."""

import os


def _float_setting(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc

    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _int_setting(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number.") from exc

    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


GEMINI_MODEL = "gemini-3.8-flash"

# Kiki joins in occasionally, and direct @mentions bypass the random chance.
REPLY_PROBABILITY = _float_setting(
    "KIKI_REPLY_PROBABILITY",
    0.18,
    minimum=0.0,
    maximum=1.0,
)
CHANNEL_COOLDOWN_SECONDS = _float_setting(
    "KIKI_CHANNEL_COOLDOWN_SECONDS",
    15.0,
    minimum=0.0,
    maximum=86_400.0,
)
CONTEXT_MESSAGE_COUNT = _int_setting(
    "KIKI_CONTEXT_MESSAGES",
    10,
    minimum=2,
    maximum=30,
)
MAX_INPUT_CHARACTERS = _int_setting(
    "KIKI_MAX_INPUT_CHARACTERS",
    1_200,
    minimum=100,
    maximum=5_000,
)
MAX_REPLY_CHARACTERS = _int_setting(
    "KIKI_MAX_REPLY_CHARACTERS",
    700,
    minimum=100,
    maximum=1_800,
)

MAX_CHANNEL_HISTORIES = 100
GEMINI_MAX_OUTPUT_TOKENS = 512
GEMINI_MAX_RETRIES = 2
MAX_CONCURRENT_GEMINI_REQUESTS = 2
