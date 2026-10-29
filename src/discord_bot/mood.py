"""Bounded fictional mood signals and concise, evidence-based summaries."""

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MoodState:
    happiness: float = 0.55
    irritation: float = 0.08
    energy: float = 0.58
    sociability: float = 0.52
    confidence: float = 0.55
    amusement: float = 0.20
    curiosity: float = 0.35
    affection: float = 0.30
    embarrassment: float = 0.10
    boredom: float = 0.22

    def as_dict(self) -> dict[str, float]:
        return {
            "happiness": self.happiness,
            "irritation": self.irritation,
            "energy": self.energy,
            "sociability": self.sociability,
            "confidence": self.confidence,
            "amusement": self.amusement,
            "curiosity": self.curiosity,
            "affection": self.affection,
            "embarrassment": self.embarrassment,
            "boredom": self.boredom,
        }

    @classmethod
    def from_dict(cls, values: dict[str, object]) -> "MoodState":
        defaults = cls().as_dict()
        parsed: dict[str, float] = {}
        for field, default in defaults.items():
            try:
                parsed[field] = _bounded(float(values.get(field, default)))
            except (TypeError, ValueError):
                parsed[field] = default
        return cls(**parsed)


@dataclass(frozen=True)
class MoodSignal:
    category: str
    reason: str
    changes: dict[str, float]


@dataclass(frozen=True)
class MoodSnapshot:
    state: MoodState
    recent_reasons: tuple[str, ...]
    interaction_count: int
    updated_at: float | None


_BASELINE = MoodState()
_DECAY_TARGET = {
    **_BASELINE.as_dict(),
    "energy": 0.38,
    "sociability": 0.42,
    "boredom": 0.35,
}
_APOLOGY = re.compile(r"\b(?:desculpa|foi mal|me perdoa|perd[aã]o)\b")
_TARGETED_INSULT = re.compile(
    r"\b(?:kiki|você|vc|tu)\b.{0,35}\b(?:burra|idiota|in[uú]til|"
    r"imprest[aá]vel|cala a boca|n[aã]o suporto você)\b"
    r"|\b(?:burra|idiota|in[uú]til|imprest[aá]vel)\b.{0,25}\b(?:kiki|você|vc|tu)\b"
)
_COMPLIMENT = re.compile(
    r"\b(?:gosto de você|gosto de ti|você [ée] incr[ií]vel|"
    r"tu [ée] incr[ií]vel|mandou bem|obrigad[oa]|valeu)\b"
)
_LAUGHTER = re.compile(r"\b(?:kkkk+|h+a+h+a+|hue+|lmao)\b")
_INTEREST = re.compile(
    r"\b(?:jogo|games?|m[uú]sica|arte|anime|meme|filme|s[eé]rie|"
    r"internet|yuri|yaoi|desenho|personagem|curiosidade)\b"
)
_BOREDOM = re.compile(r"\b(?:t[eé]dio|entediad[oa]|sem nada pra fazer)\b")
_GREETING = re.compile(r"^(?:oi|ol[aá]|eai|e a[ií]|ei|bom dia|boa noite)\b")


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, value))


def apply_decay(state: MoodState, elapsed_seconds: float) -> MoodState:
    """Gently return simulated feelings toward a stable baseline over six hours."""
    if elapsed_seconds <= 0:
        return state
    blend = 1.0 - math.exp(-elapsed_seconds / 21_600)
    values = state.as_dict()
    baseline = _DECAY_TARGET
    for field, value in values.items():
        values[field] = _bounded(value + (baseline[field] - value) * blend)
    return MoodState(**values)


def apply_signal(state: MoodState, signal: MoodSignal) -> MoodState:
    """Apply one small, context-derived change and clamp every dimension."""
    values = state.as_dict()
    for field, amount in signal.changes.items():
        if field in values:
            values[field] = _bounded(values[field] + amount)
    return MoodState(**values)


def classify_mood_signal(
    text: str,
    *,
    addressed_to_kiki: bool,
    is_creator: bool = False,
) -> MoodSignal | None:
    """Map clear conversational cues to small mood changes; ignore neutral text."""
    normalized = text.casefold()

    if addressed_to_kiki and _TARGETED_INSULT.search(normalized):
        return MoodSignal(
            category="hostility",
            reason="uma mensagem diretamente dirigida a mim veio hostil",
            changes={"irritation": 0.07, "energy": -0.02, "confidence": -0.02},
        )
    if addressed_to_kiki and _APOLOGY.search(normalized):
        return MoodSignal(
            category="apology",
            reason="alguém se explicou ou pediu desculpas",
            changes={"irritation": -0.06, "happiness": 0.02, "sociability": 0.02},
        )
    if addressed_to_kiki and _COMPLIMENT.search(normalized):
        changes = {"happiness": 0.035, "affection": 0.035, "sociability": 0.02}
        if is_creator:
            changes["confidence"] = 0.02
        return MoodSignal(
            category="kindness",
            reason="recebi uma interação gentil",
            changes=changes,
        )
    if _BOREDOM.search(normalized):
        return MoodSignal(
            category="boredom",
            reason="alguém comentou que estava entediado",
            changes={"curiosity": 0.025, "sociability": 0.02, "boredom": 0.025},
        )
    if _LAUGHTER.search(normalized):
        return MoodSignal(
            category="humor",
            reason="a conversa teve um sinal de humor",
            changes={"amusement": 0.05, "happiness": 0.02, "energy": 0.015},
        )
    if _INTEREST.search(normalized):
        return MoodSignal(
            category="interest",
            reason="apareceu um assunto que desperta minha curiosidade",
            changes={"curiosity": 0.04, "energy": 0.015},
        )
    if addressed_to_kiki and _GREETING.search(normalized):
        reason = (
            "a criadora apareceu para conversar"
            if is_creator
            else "alguém veio falar comigo"
        )
        return MoodSignal(
            category="greeting",
            reason=reason,
            changes={"happiness": 0.025, "sociability": 0.035, "affection": 0.015},
        )
    return None


def mood_prompt_context(snapshot: MoodSnapshot) -> str:
    """Give Gemini mood facts, not private message text or hidden reasoning."""
    if not snapshot.recent_reasons:
        return (
            "Estado simulado: neutro, sem interações recentes suficientes para "
            "sugerir uma mudança. Não invente um motivo nem narre o humor sem necessidade."
        )

    state = snapshot.state
    indicators = (
        f"felicidade={round(state.happiness * 100)}/100, "
        f"irritação={round(state.irritation * 100)}/100, "
        f"energia={round(state.energy * 100)}/100, "
        f"diversão={round(state.amusement * 100)}/100, "
        f"curiosidade={round(state.curiosity * 100)}/100"
    )
    reasons = "; ".join(snapshot.recent_reasons[:3])
    return (
        f"Humor fictício atual (sutil, não precisa ser anunciado): {indicators}. "
        f"Fatores recentes registrados: {reasons}. "
        "Use isso apenas para ajustar o tom; não invente emoções ou acontecimentos."
    )


def format_huh_report(snapshot: MoodSnapshot) -> str:
    """Render /huh from stored state and recorded reason labels."""
    if not snapshot.recent_reasons:
        return (
            "ainda não tenho interações recentes suficientes pra dizer como tô. "
            "não vou inventar um humor só pra parecer profunda."
        )

    state = snapshot.state
    if state.irritation >= 0.58:
        description = "com a paciência um pouco curta"
    elif state.energy <= 0.38:
        description = "mais quieta e com pouca energia"
    elif state.amusement >= 0.55:
        description = "mais leve e achando graça das coisas"
    elif state.curiosity >= 0.58:
        description = "curiosa e ligada no que tá rolando"
    elif state.happiness >= 0.64:
        description = "de bom humor e sociável"
    else:
        description = "relativamente de boa"

    indicators = (
        f"energia {round(state.energy * 100)}/100 · "
        f"irritação {round(state.irritation * 100)}/100 · "
        f"curiosidade {round(state.curiosity * 100)}/100 · "
        f"diversão {round(state.amusement * 100)}/100"
    )
    reasons = "; ".join(snapshot.recent_reasons[:3])
    return (
        f"humor simulado: tô {description}.\n"
        f"indicadores: {indicators}.\n"
        f"motivos recentes: {reasons}."
    )
