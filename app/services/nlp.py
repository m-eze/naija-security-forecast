"""
NLP pipeline for security news classification.

Deliberately keyword-based (not ML) for:
  - Speed (no model loading per request)
  - Transparency (explainable for users)
  - Nigeria-specificity (fine-tuned vocabulary, not generic sentiment)

Three tasks:
  1. Security relevance classification
  2. Sentiment scoring (-1 to +1)
  3. Location extraction (state + LGA name from text)
"""
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Security vocabulary — Nigeria-specific
# ---------------------------------------------------------------------------

VIOLENCE_TERMS = {
    "attack", "attacked", "attacks", "kill", "killed", "kills", "dead", "death",
    "deaths", "murder", "murdered", "shoot", "shot", "shooting", "bomb", "bombed",
    "bombing", "explosion", "blast", "ambush", "massacre", "slaughter", "kidnap",
    "kidnapped", "kidnapping", "abduct", "abducted", "abduction", "hostage",
    "ransom", "execute", "executed", "execution", "assassinate", "assassination",
    "behead", "beheaded", "beheading", "torture", "raid", "raided", "robbery",
    "robbed", "armed robbery", "cult", "cultist", "cultism", "clash", "clashes",
    "violence", "riot", "unrest", "crisis", "genocide", "ethnic cleansing",
    "farmer herder", "bandit", "bandits", "banditry", "insurgent", "insurgency",
    "terrorism", "terrorist", "terrorists", "gunmen", "gunman", "armed men",
    "gunfire", "crossfire", "iED", "landmine", "suicide bomber", "car bomb",
    "pipeline vandal", "oil theft", "pipeline explosion", "community attack",
    "community clashes", "sack", "sacked", "displace", "displaced", "displacement",
    "arson", "burn", "burned", "set ablaze", "houses burnt", "village razed",
}

NIGERIA_ARMED_GROUPS = {
    "boko haram", "iswap", "islamic state west africa", "ansaru",
    "bandits", "lakurawa", "fulani herdsmen", "herders", "militia",
    "ipob", "esn", "eastern security network", "biafra", "massob",
    "opc", "odua peoples congress", "avengers", "niger delta avengers",
    "black axe", "eiye", "vikings confraternity", "buccaneer",
    "pirates", "kidnappers", "armed robbers", "cultists",
}

SECURITY_ACTORS = {
    "army", "military", "soldiers", "troops", "police", "police force",
    "npf", "naf", "nigerian air force", "navy", "dss", "nsa", "nscdc",
    "customs", "immigration", "vigilante", "amotekun", "hisbah",
    "civilian jtt", "joint task force", "operation safe haven",
    "operation hadarin daji", "operation whirl punch", "operation thunder strike",
}

RESOLUTION_TERMS = {
    "rescue", "rescued", "rescue operation", "recover", "recovered", "recovery",
    "arrest", "arrested", "apprehend", "apprehended", "neutralise", "neutralized",
    "killed in gun battle", "repel", "repelled", "defeat", "defeated",
    "peace deal", "ceasefire", "surrender", "surrendered", "jail", "jailed",
    "prosecute", "prosecuted", "conviction", "convicted", "sentence",
}

# All security-relevant terms combined (for quick relevance check)
_ALL_SECURITY = VIOLENCE_TERMS | {g.split()[0] for g in NIGERIA_ARMED_GROUPS} | SECURITY_ACTORS

# Negative sentiment contributors (weighted)
_NEGATIVE = {
    **{t: 2 for t in VIOLENCE_TERMS},
    **{g.split()[0]: 3 for g in NIGERIA_ARMED_GROUPS},
}
# Positive/resolution contributors
_POSITIVE = {t: 1 for t in RESOLUTION_TERMS}


# ---------------------------------------------------------------------------
# Nigeria geography — loaded once at module level
# ---------------------------------------------------------------------------

NIGERIA_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue",
    "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT",
    "Abuja", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi",
    "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun",
    "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
]

# Map alternative names to canonical state names
STATE_ALIASES = {
    "abuja": "FCT",
    "fct": "FCT",
    "federal capital territory": "FCT",
    "akwa ibom": "Akwa Ibom",
    "cross river": "Cross River",
}

_STATE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(NIGERIA_STATES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NLPResult:
    security_relevant: bool
    relevance_confidence: float        # 0.0 – 1.0
    sentiment_score: float             # -1.0 to +1.0
    sentiment_label: str               # "negative" | "neutral" | "positive"
    extracted_state: str | None
    extracted_lga: str | None          # raw text mention, not resolved ID
    extracted_entities: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def classify_security_relevance(headline: str, body: str = "") -> tuple[bool, float]:
    """Return (is_relevant, confidence 0-1)."""
    text = f"{headline} {body}".lower()
    tokens = set(_tokenise(text))

    # Check for any violence/actor/security-force term
    hits = tokens & {t.lower() for t in _ALL_SECURITY}

    # Check multi-word group names
    group_hits = sum(1 for g in NIGERIA_ARMED_GROUPS if g in text)

    total_hits = len(hits) + group_hits

    if total_hits == 0:
        return False, 0.0

    # Headline hit is a strong signal
    headline_tokens = set(_tokenise(headline))
    headline_hits = headline_tokens & {t.lower() for t in _ALL_SECURITY}
    headline_group_hits = sum(1 for g in NIGERIA_ARMED_GROUPS if g in headline.lower())

    if headline_hits or headline_group_hits:
        confidence = min(0.95, 0.6 + total_hits * 0.05)
    else:
        confidence = min(0.75, 0.3 + total_hits * 0.04)

    return confidence >= 0.4, round(confidence, 3)


def score_sentiment(text: str) -> tuple[float, str]:
    """Return (score -1 to +1, label)."""
    tokens = _tokenise(text)
    neg = sum(_NEGATIVE.get(t, 0) for t in tokens)
    pos = sum(_POSITIVE.get(t, 0) for t in tokens)

    total = neg + pos
    if total == 0:
        return 0.0, "neutral"

    raw = (pos - neg) / total
    score = round(max(-1.0, min(1.0, raw)), 3)

    if score <= -0.15:
        label = "negative"
    elif score >= 0.15:
        label = "positive"
    else:
        label = "neutral"

    return score, label


def extract_locations(text: str, lga_names: list[str] | None = None) -> tuple[str | None, str | None]:
    """
    Return (state, lga_text_mention).
    lga_names: list of canonical LGA names loaded from DB — pass for richer matching.
    """
    # State extraction
    state: str | None = None
    match = _STATE_PATTERN.search(text)
    if match:
        raw_state = match.group(1)
        state = STATE_ALIASES.get(raw_state.lower(), raw_state)

    # LGA extraction — check against known LGA names if provided
    lga: str | None = None
    if lga_names:
        text_lower = text.lower()
        for name in lga_names:
            if re.search(r"\b" + re.escape(name.lower()) + r"\b", text_lower):
                lga = name
                break

    return state, lga


def extract_entities(text: str) -> dict:
    """Extract structured entities: event types, actors mentioned."""
    text_lower = text.lower()
    found_groups = [g for g in NIGERIA_ARMED_GROUPS if g in text_lower]
    found_actors = [a for a in SECURITY_ACTORS if re.search(r"\b" + re.escape(a) + r"\b", text_lower)]

    violence_types = []
    for term in ["bombing", "kidnapping", "shooting", "ambush", "massacre", "robbery", "banditry", "clashes"]:
        if term in text_lower:
            violence_types.append(term)

    return {
        "armed_groups": found_groups[:5],
        "security_actors": found_actors[:5],
        "violence_types": violence_types,
    }


def process_article(
    headline: str,
    body: str,
    lga_names: list[str] | None = None,
) -> NLPResult:
    """Full NLP pipeline for a single article."""
    full_text = f"{headline}. {body}"

    is_relevant, confidence = classify_security_relevance(headline, body)
    sentiment_score, sentiment_label = score_sentiment(full_text)
    state, lga = extract_locations(full_text, lga_names)
    entities = extract_entities(full_text) if is_relevant else {}

    return NLPResult(
        security_relevant=is_relevant,
        relevance_confidence=confidence,
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        extracted_state=state,
        extracted_lga=lga,
        extracted_entities=entities,
    )
