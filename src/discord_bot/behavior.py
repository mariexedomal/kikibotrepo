"""Lightweight conversation cues that keep Discord message handling bounded."""

import re
import unicodedata


_KIKI_WORD = re.compile(r"(?<![\w])kiki(?![\w])", re.IGNORECASE)
_ADDRESS_PREFIX = re.compile(
    r"^\s*(?:(?:ei|eai|oi|olá|ola|hey|mano|cara|amiga|amigo|gente|aí|ai|ô)\s+)*kiki\b",
    re.IGNORECASE,
)
_GREETING_NAME = re.compile(
    r"^\s*(?:oi|olá|ola|eai|e aí|hey)\s*[, ]+\s*kiki\b",
    re.IGNORECASE,
)
_DIRECT_CUE = re.compile(
    r"^(?:\s*[,!?…]+\s*|"
    r"\s+(?:tu|você|vc|cê|vcs|te|tua|teu|me|olha|escuta|fala|vem|vê|"
    r"responde|explica|conta|ajuda|diz|eai|e aí)\b)",
    re.IGNORECASE,
)
_QUESTION_TO_KIKI = re.compile(
    r"\b(?:kiki\s*[,;:]?\s*(?:tu|você|vc|cê)\b|"
    r"e\s+a\s+kiki\s*[,;:]?\s*(?:o\s+que|que|tu|você)\b|"
    r"(?:pra|para)\s+kiki\b).*[?？！]",
    re.IGNORECASE,
)
_REQUEST_FOR_KIKI = re.compile(
    r"\b(?:alguém|alguem|pode|podem|me|por favor)\b.*"
    r"\b(?:explica|explicar|conta|contar|mostra|mostrar|manda|mandar)\b.*"
    r"\b(?:pra|para)\s+kiki\b",
    re.IGNORECASE,
)
_THIRD_PERSON_SHIFT = re.compile(
    r"^(?:mudando de assunto|outra coisa|falando de outra coisa|"
    r"nada a ver, mas|mudando totalmente de assunto)\b",
    re.IGNORECASE,
)
_FOLLOWUP_START = re.compile(
    r"^(?:sim|s|não|nao|também|tbm|tô|to|estou|sou|acho|sei|"
    r"pois é|pois eh|pior que|aham|uhum|então|entao|mas|e tu|e você|"
    r"e vc|tudo bem|tudo certo|valeu|obrigad[oa]|desculpa|foi mal|"
    r"kkkk+|h+a+h+a+|hue+)\b",
    re.IGNORECASE,
)
_RELEVANT_TERMS = re.compile(
    r"\b(?:jogo|games?|m[uú]sica|arte|anime|meme|filme|s[eé]rie|"
    r"internet|yuri|yaoi|peito|seios|desenho|personagem|"
    r"meu deus|mds|pior que|acho que|ser[aá] que|algu[eé]m|"
    r"descobri|kkkk+|h+a+h+a+)\b",
    re.IGNORECASE,
)
_PROTECTED_SPAN = re.compile(
    r"```[\s\S]*?(?:```|$)"
    r"|`[^`\n]*(?:`|$)"
    r"|https?://[^\s<>()]+"
    r"|<(?:(?:@!?|@&|#)\d+|a?:[A-Za-z0-9_]+:\d+)>"
    r"|(?<![A-Za-z0-9_])(?:[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+|"
    r"[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*|"
    r"[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]*)+)(?![A-Za-z0-9_])"
)
_BOT_MENTION = re.compile(r"<@!?(\d+)>")


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace for small, local text heuristics."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def is_explicitly_addressed(text: str) -> bool:
    """Recognize likely direct address while ignoring most third-person mentions."""
    normalized = normalize_text(text)
    name_match = _KIKI_WORD.search(normalized)
    if name_match is None:
        return False

    if _GREETING_NAME.match(normalized):
        return True
    prefix_match = _ADDRESS_PREFIX.match(normalized)
    if prefix_match is not None:
        remainder = normalized[prefix_match.end() :]
        if not remainder or re.fullmatch(r"[\s?!.,…]+", remainder):
            return True
        if _DIRECT_CUE.match(remainder):
            return True

    if _QUESTION_TO_KIKI.search(normalized) or _REQUEST_FOR_KIKI.search(normalized):
        return True

    # A conversational vocative can appear after an opening phrase.
    before_name = normalized[: name_match.start()].rstrip()
    if re.search(r"(?:^|[,!?…]\s*|^)(?:mano|cara|gente|ei|oi)\s*$", before_name):
        return True
    return False


def is_conversation_followup(text: str) -> bool:
    """Recognize short replies that plausibly continue a just-active exchange."""
    normalized = normalize_text(text)
    if not normalized or len(normalized) > 400 or _THIRD_PERSON_SHIFT.match(normalized):
        return False
    if "?" in normalized or "？" in normalized:
        return len(normalized) <= 240
    if _FOLLOWUP_START.match(normalized):
        return True
    return len(normalized) <= 120 and bool(
        re.match(r"^(?:e|mas|aí|ai|então|entao)\s+", normalized)
    )


def is_relevant_spontaneous_candidate(text: str) -> bool:
    """Filter out low-information chatter before spending a Gemini request."""
    normalized = normalize_text(text)
    if len(normalized) < 10 or normalized.startswith("/"):
        return False
    if "?" in normalized or "？" in normalized:
        return len(normalized) >= 12
    if _RELEVANT_TERMS.search(normalized):
        return True
    return len(normalized) >= 55 and bool(re.search(r"[.!…]", normalized))


def remove_bot_mention(text: str, bot_id: int) -> str:
    """Remove only Kiki's mention token before adding a message to context."""
    return _BOT_MENTION.sub(
        lambda match: "" if int(match.group(1)) == bot_id else match.group(0),
        text,
    ).strip()


def lowercase_prose(text: str) -> str:
    """Lowercase prose while preserving code, URLs, Discord tags, and identifiers."""
    parts: list[str] = []
    cursor = 0
    for match in _PROTECTED_SPAN.finditer(text):
        parts.append(text[cursor : match.start()].lower())
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(text[cursor:].lower())
    return "".join(parts).strip()
