"""Lightweight conversation cues that keep Discord message handling bounded."""

import re
import unicodedata

from .interests import interest_context_for


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
_AI_TERMS = re.compile(
    r"\b(?:artificial intelligence|intelig[eê]ncia artificial|"
    r"ia generativa|generative ai|chat\s*gpt|chatgpt|gemini|claude|"
    r"anthropic|openai|llms?|large language models?|modelos? de linguagem|"
    r"language models?|machine learning|aprendizado de m[aá]quina|"
    r"deep learning|redes neurais|neural networks?|ai agents?|"
    r"agentes? de ia|chatbots? de ia|ai chatbots?)\b",
    re.IGNORECASE,
)
_AI_ABBREVIATION = re.compile(r"(?<!\w)(?:AI|IA)(?!\w)")
_AI_ABBREVIATION_CONTEXT = re.compile(
    r"(?<!\w)(?:ai|ia)(?!\w)\s+"
    r"(?:bot|chatbot|modelo|model|agente|agent|generativa?|generative)\b",
    re.IGNORECASE,
)
_K_LAUGHTER = re.compile(r"(?<!\w)k{3,}(?!\w)", re.IGNORECASE)
_MACHINE_PHRASE = re.compile(r"\bturn off the machine\b", re.IGNORECASE)
_ALL_CAPS_WORD = re.compile(r"(?<!\w)[A-ZÀ-Þ][A-ZÀ-Þ0-9_-]{1,}(?!\w)")
_LATIN_LETTER = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


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
    if interest_context_for([text]):
        return True
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
    """Lowercase prose while retaining deliberate laughter, emphasis, and glitch text."""
    parts: list[str] = []
    cursor = 0
    for match in _PROTECTED_SPAN.finditer(text):
        parts.append(_format_prose(text[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(_format_prose(text[cursor:]))
    return "".join(parts).strip()


def _format_prose(text: str) -> str:
    """Apply Kiki's lower-case style without erasing a few intentional exceptions."""
    if not text:
        return text

    preserved: dict[str, str] = {}

    def protect(value: str) -> str:
        key = f"\u0000{len(preserved)}\u0000"
        preserved[key] = value
        return key

    text = _MACHINE_PHRASE.sub(
        lambda _: protect("TURN OFF THE MACHINE"), text
    )
    text = _K_LAUGHTER.sub(lambda match: protect(match.group(0).upper()), text)

    has_letters = bool(_LATIN_LETTER.search(text))
    all_caps_sentence = has_letters and not re.search(r"[a-zà-öø-ÿ]", text)
    emphasis_count = 0

    def format_caps(match: re.Match[str]) -> str:
        nonlocal emphasis_count
        word = match.group(0)
        # A fully capitalized sentence is not emphasis. Keep short common acronyms.
        if all_caps_sentence:
            if word in {"API", "HTTP", "SQL", "URL", "JSON", "CPU", "GPU", "AI", "IA"}:
                return word
            return word.lower()
        if word in {"API", "HTTP", "SQL", "URL", "JSON", "CPU", "GPU", "AI", "IA"}:
            return word
        if not text[: match.start()].strip() or re.search(
            r"[.!?…]\s*$", text[: match.start()]
        ):
            return word.lower()
        emphasis_count += 1
        return word if emphasis_count <= 2 else word.lower()

    formatted = _ALL_CAPS_WORD.sub(format_caps, text).lower()
    for key, value in preserved.items():
        formatted = formatted.replace(key, value)
    return formatted


def format_reply(text: str, limit: int) -> str:
    """Format and trim a reply at a sentence or word boundary."""
    formatted = lowercase_prose(text)
    if len(formatted) <= limit:
        return formatted

    shortened = formatted[:limit].rstrip()
    sentence_end = max(
        shortened.rfind("."),
        shortened.rfind("!"),
        shortened.rfind("?"),
        shortened.rfind("…"),
    )
    if sentence_end >= int(limit * 0.55):
        return shortened[: sentence_end + 1].rstrip()

    word_end = shortened.rfind(" ")
    if word_end > 0:
        shortened = shortened[:word_end].rstrip()
    return f"{shortened}…"


def is_ai_related(text: str) -> bool:
    """Detect clear AI topics locally without using a model call."""
    return bool(
        _AI_TERMS.search(text)
        or _AI_ABBREVIATION.search(text)
        or _AI_ABBREVIATION_CONTEXT.search(text)
    )
