"""Editable behavior and safety limits for Kiki."""

import os


def _id_set(name: str) -> frozenset[int]:
    raw_value = os.getenv(name, "")
    values: set[int] = set()
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        if not item.isdecimal():
            raise ValueError(f"{name} must contain comma-separated Discord IDs.")
        values.add(int(item))
    return frozenset(values)


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
USER_COOLDOWN_SECONDS = _float_setting(
    "KIKI_USER_COOLDOWN_SECONDS",
    30.0,
    minimum=0.0,
    maximum=86_400.0,
)
CONVERSATION_CONTINUATION_SECONDS = _int_setting(
    "KIKI_CONVERSATION_CONTINUATION_SECONDS",
    90,
    minimum=15,
    maximum=600,
)
MAX_CONVERSATION_FOLLOWUPS = _int_setting(
    "KIKI_MAX_CONVERSATION_FOLLOWUPS",
    4,
    minimum=1,
    maximum=10,
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
MAX_SEEN_MESSAGES = 2_000
MAX_TRACKED_BOT_REPLIES = 1_000
GEMINI_MAX_OUTPUT_TOKENS = 512
GEMINI_MAX_RETRIES = 2
MAX_CONCURRENT_GEMINI_REQUESTS = 2
STATE_DB_PATH = os.getenv("KIKI_STATE_DB_PATH", "data/kiki-state.sqlite3")
CREATOR_USER_IDS = _id_set("KIKI_CREATOR_USER_IDS")
